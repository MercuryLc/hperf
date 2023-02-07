from datetime import datetime
from typing import Sequence, Union
import subprocess
import os
import logging
import re
import paramiko


class Connector:
    """
    The interface of `Connector`.
    `Connector` provides various useful method for executing commands or shell scripts.
    """

    def __init__(self, configs: dict) -> None:
        pass

    def get_test_dir_path(self) -> str:
        pass

    def run_script(self, script: str) -> int:
        pass

    def run_command(self, command_args: Union[Sequence[str], str]) -> str:
        pass


class LocalConnector(Connector):
    """
    `LocalConnector` is extended from `Connector`, which provide useful method for executing commands or shell scripts on local SUT.
    """

    def __init__(self, configs: dict) -> None:
        """
        Constructor of `LocalConnector`. 
        When instantiated, it will try to access the temporary directory (`.configs["tmp_dir"]`)
        specified by command line options `--tmp-dir` (`/tmp/hperf/` by default) 
        and create an unique test directory in the temporary directory. 
        The test directory is for this run of hperf and used to save profiling scripts, raw performance data, analysis results, log file, etc.

        Note: this action may change the value of `configs["tmp_dir"]` if it cannot be accessed.
        """
        self.configs = configs
        self.logger = logging.getLogger("hperf")

        self.tmp_dir = ""
        # if the temporary directory is not exist, try to create the directory
        if os.path.exists(configs["tmp_dir"]):
            if os.access(configs["tmp_dir"], os.R_OK | os.W_OK):
                self.tmp_dir = os.path.abspath(configs["tmp_dir"])
                self.logger.debug(
                    f"set temporary directory: {self.tmp_dir} (already exists)")
            else:
                bad_tmp_dir = os.path.abspath(configs["tmp_dir"])
                self.logger.warning(
                    f"invalid temporary directory: {bad_tmp_dir} (already exists but has no R/W permission)")
                self.logger.warning("reset temporary directory: '/tmp/hperf/'")
                os.makedirs("/tmp/hperf/", exist_ok=True)
                # Note: this action will change the value of 'configs["tmp_dir"]'
                self.tmp_dir = configs["tmp_dir"] = "/tmp/hperf/"
        else:
            try:
                os.makedirs(configs["tmp_dir"])
                self.tmp_dir = os.path.abspath(configs["tmp_dir"])
                self.logger.debug(
                    f"success to create the temporary directory {self.tmp_dir}")
            except OSError:
                bad_tmp_dir = os.path.abspath(configs["tmp_dir"])
                self.logger.warning(
                    f"invalid temporary directory: {bad_tmp_dir} (fail to create the temporary directory)")
                self.logger.warning("reset temporary directory: '/tmp/hperf/'")
                os.makedirs("/tmp/hperf/", exist_ok=True)
                # Note: this action will change the value of 'configs["tmp_dir"]'
                self.tmp_dir = configs["tmp_dir"] = "/tmp/hperf/"

        # search the temporary directory (`.tmp_dir`) and get a string with an unique test id,
        # then create a sub-directory named by this string in the temporary directory for saving files for profiling.
        self.test_id = self.__find_test_id()
        os.makedirs(self.get_test_dir_path())
        self.logger.info(f"test directory: {self.get_test_dir_path()}")

    def __find_test_id(self) -> str:
        """
        Search the temporary directory (`.tmp_dir`) and return a string with an unique test directory.

        e.g. In the temporary directory, there are many sub-directory named `<date>_test<id>` for different runs.
        If `20221206_test001` and `202211206_test002` are exist, it will return `202211206_test003`.
        :return: a directory name with an unique test id for today
        """
        today = datetime.now().strftime("%Y%m%d")
        max_id = 0
        pattern = f"{today}_test(\d+)"
        for item in os.listdir(self.tmp_dir):
            path = os.path.join(self.tmp_dir, item)
            if os.path.isdir(path):
                obj = re.search(pattern, path)
                if obj:
                    found_id = int(obj.group(1))
                    if found_id > max_id:
                        max_id = found_id
        test_id = f"{today}_test{str(max_id + 1).zfill(3)}"
        return test_id

    def get_test_dir_path(self) -> str:
        """
        Get the abusolute path of the unique test directory for this test. 
        :return: an abusolute path of the unique test directory for this test
        """
        return os.path.join(self.tmp_dir, self.test_id)

    def run_script(self, script: str) -> int:
        """
        Create and run a script on SUT, then wait for the script finished. 
        If the returned code is not eqaul to 0, it will generate a debug log message. 
        :param `script`: a string of shell script
        :return: the returned code of executing the shell script
        """
        script_path = self.__generate_script(script)
        self.logger.debug(f"run script: {script_path}")
        process = subprocess.Popen(
            ["bash", f"{script_path}"], stdout=subprocess.PIPE)
        ret_code = process.wait()
        self.logger.debug(f"finish script: {script_path}")
        return ret_code

    def __generate_script(self, script: str) -> str:
        """
        Generate a profiling script on SUT. 
        :param `script`: the string of shell script
        :return: path of the script on the SUT
        """
        script_path = os.path.join(self.tmp_dir, self.test_id, "perf.sh")
        with open(script_path, 'w') as f:
            f.write(script)
        self.logger.debug(f"generate script: {script_path}")
        return script_path

    def run_command(self, command_args: Union[Sequence[str], str]) -> str:
        """
        Run a command on SUT, then return the stdout output of executing the command. 
        The output is decoded by 'utf-8'. 
        :param `command_args`: a sequence of program arguments, e.g. `["ls", "/home"]`, or a string of command, e.g. `"ls /home"`
        :return: stdout output
        """
        if isinstance(command_args, list):
            output = subprocess.Popen(command_args, stdout=subprocess.PIPE).communicate()[0]
        else:
            output = subprocess.Popen(command_args, shell=True, stdout=subprocess.PIPE).communicate()[0]
        output = output.decode("utf-8")
        return output


class RemoteConnector(Connector):
    """
    `RemoteConnector` is extended from `Connector`, which provide useful method for executing commands or shell scripts on remote SUT. 
    The remote SUT is can not be accessed locally, so that the operations rely on SSH / SFTP connection to remote SUT. 
    """

    def __init__(self, configs: dict) -> None:
        """
        Constructor of `LocalConnector`. 
        When instantiated, it will try to access the temporary directory (`.configs["tmp_dir"]`, can be accessed locally, 
        specified by command line options `--tmp-dir` (`/tmp/hperf/` by default) 
        and create an unique test directory in the temporary directory. 
        The test directory is for this run of hperf and used to save profiling scripts, raw performance data, analysis results, log file, etc. 

        The local temporary directory is named `.local_tmp_dir`.

        Note: this action may change the value of `configs["tmp_dir"]` if it cannot be accessed.

        Unlike `LocalConnector`, `RemoteConnector` relys on SSH / SFTP connection to operate remote SUT. 
        So that the SSH and SFTP session will be opened by paramiko. 
        Finally a remote temporary directory will be created (`~/.hperf/`) because scripts need to upload to remote SUT before executing 
        and the output need to download from remote SUT. The remote directory is for these temporary files. 

        The remote temporary directory is named `.remote_tmp_dir`
        """
        self.configs = configs
        self.logger = logging.getLogger("hperf")

        self.remote_tmp_dir: str = ""
        self.local_tmp_dir: str = ""

        # step 1. find or create the local temporary directory
        # if the local temporary directory is not exist, try to create the directory
        specified_tmp_dir = configs["tmp_dir"]    # user-specified temporary directory by the 'tmp-dir' command line option
        if os.path.exists(specified_tmp_dir):
            if os.access(specified_tmp_dir, os.R_OK | os.W_OK):
                self.local_tmp_dir = os.path.abspath(specified_tmp_dir)
                self.logger.debug(
                    f"set local temporary directory: {self.local_tmp_dir} (already exists)")
            else:
                bad_local_tmp_dir = os.path.abspath(specified_tmp_dir)    # does not have R/W permission
                self.logger.warning(
                    f"invalid local temporary directory: {bad_local_tmp_dir} (already exists but has no R/W permission)")
                self.logger.warning("reset the local temporary directory to '/tmp/hperf/'")
                os.makedirs("/tmp/hperf/", exist_ok=True)
                # Note: this action will change the value of 'configs["tmp_dir"]'
                self.local_tmp_dir = configs["tmp_dir"] = "/tmp/hperf/"
        else:
            try:
                os.makedirs(specified_tmp_dir)
                self.local_tmp_dir = os.path.abspath(specified_tmp_dir)
                self.logger.debug(
                    f"success to create the local temporary directory {self.local_tmp_dir}")
            except OSError:
                bad_local_tmp_dir = os.path.abspath(specified_tmp_dir)
                self.logger.warning(
                    f"invalid local temporary directory: {bad_local_tmp_dir} (fail to create the temporary directory)")
                self.logger.warning("reset the local temporary directory to '/tmp/hperf/'")
                os.makedirs("/tmp/hperf/", exist_ok=True)
                # Note: this action will change the value of 'configs["tmp_dir"]'
                self.local_tmp_dir = configs["tmp_dir"] = "/tmp/hperf/"
        
        # search the local temporary directory (self.local_tmp_dir) and get a string with an unique test id,
        # then create a sub-directory named by this string in the local temporary directory for saving files for profiling.
        self.test_id = self.__find_test_id()
        os.makedirs(self.get_test_dir_path())
        self.logger.info(f"test directory (local): {self.get_test_dir_path()}")

        # step 2. open a SSH session
        # paramiko SSH connection configurations
        self.hostname: str = self.configs["hostname"]
        self.username: str = self.configs["username"]
        self.password: str = self.configs["password"]
        # TODO: the port of SSH is 22 by default. in future, the port can be specified explictly by command line option '-p'.
        self.port: int = 22

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy)   # for the first connection
        try:
            self.client.connect(self.hostname, self.port, self.username, self.password)
        except paramiko.BadHostKeyException:
            self.logger.error("the server's host key could not be verified")
            exit(-1)
        except paramiko.AuthenticationException:
            self.logger.error("authentication failed")
            exit(-1)
        except paramiko.SSHException:
            self.logger.error("connecting or establishing an SSH session failed")
            exit(-1)

        # step 3. open a SFTP session
        self.sftp = self.client.open_sftp()
        
        # step 4. create a temporary directory on the remote SUT through SFTP session
        # the temporary directory is './.hperf/' by default. if it does not exist, hperf will create the directory.
        default_remote_tmp_dir = "./.hperf/"
        # the initial working directory is "~/" 
        file_list = self.sftp.listdir(".")    # list all files (including directories) in current working directory
        if ".hperf" in file_list:    # directory ./.hperf/ exists on the remote SUT
            self.logger.debug(f"directory {default_remote_tmp_dir} exists on the remote SUT")
            try:
                self.sftp.chdir(default_remote_tmp_dir)    # change working directory: ./.hperf/
                for file in self.sftp.listdir("."):    # delete all files in ./.hperf/
                    self.sftp.remove(file)
            except IOError:
                self.logger.error("SFTP session failed")
                exit(-1)
            finally:
                self.sftp.chdir()    # reset working directory to ./
        else:    # directory ./.hperf/ does not exist on the remote SUT
            self.logger.debug(f"directory {default_remote_tmp_dir} does not exist on the remote SUT")
            self.sftp.mkdir(default_remote_tmp_dir)

        self.remote_tmp_dir = default_remote_tmp_dir

        self.logger.debug(f"remote temporary directory: {self.remote_tmp_dir}")

    def __find_test_id(self) -> str:
        """
        Search the local temporary directory (`.tmp_dir`) and return a string with an unique test directory.

        e.g. In the local temporary directory, there are many sub-directory named `<date>_test<id>` for different runs.
        If `20221206_test001` and `202211206_test002` are exist, it will return `202211206_test003`.
        :return: a directory name with an unique test id for today (can be accessed locally)
        """
        today = datetime.now().strftime("%Y%m%d")
        max_id = 0
        pattern = f"{today}_test(\d+)"
        for item in os.listdir(self.local_tmp_dir):
            path = os.path.join(self.local_tmp_dir, item)
            if os.path.isdir(path):
                obj = re.search(pattern, path)
                if obj:
                    found_id = int(obj.group(1))
                    if found_id > max_id:
                        max_id = found_id
        test_id = f"{today}_test{str(max_id + 1).zfill(3)}"
        return test_id

    def get_test_dir_path(self) -> str:
        """
        Get the abusolute path of the unique test directory for this test. 
        :return: an abusolute path of the unique test directory for this test (can be accessed locally)
        """
        return os.path.join(self.local_tmp_dir, self.test_id)
    
    def run_command(self, command_args: Sequence[str]) -> str:
        """
        Run a command on SUT, then return the stdout output of executing the command. 
        The output is decoded by 'utf-8'. 
        :param `command_args`: a sequence of program arguments, e.g. `["ls", "/home"]`, or a string of command, e.g. `"ls /home"`
        :return: stdout output
        """
        if isinstance(command_args, list):
            command: str = " ".join(command_args)
        else:
            command: str = command_args
        try:
            self.logger.debug(f"execute command on remote: {command}")
            _, stdout, _ = self.client.exec_command(command)
            ret_code = stdout.channel.recv_exit_status()
            self.logger.debug(f"finished with exit code {ret_code}")
            if ret_code != 0:
                self.logger.debug(f"executing command {command} with an exit code of {ret_code}")
            else:
                output = stdout.read().decode("utf-8")
                self.logger.debug(f"stdout of command {command}: \n{output}")
                return output
        except paramiko.SSHException:
            self.logger.error("executing command through SSH connection failed")
            self.client.close()
            exit(-1)
        except RuntimeError:
            self.logger.error(f"executing command {command} failed")
            self.client.close()
            exit(-1)
    
    def run_script(self, script: str) -> int:
        """
        Create and run a script on SUT, then wait for the script finished. 
        If the returned code is not eqaul to 0, it will generate a debug log message. 
        :param `script`: a string of shell script
        :return: the returned code of executing the shell script
        """
        # step 1. generate a script on remote SUT
        remote_script_path = self.__generate_script(script)

        # step 2. run the script by bash
        self.logger.debug(f"run script on remote SUT: {remote_script_path}")
        _, stdout, _ = self.client.exec_command(f"bash {remote_script_path}")
        ret_code = stdout.channel.recv_exit_status()
        self.logger.debug(f"finished with exit code {ret_code}")
        if ret_code != 0:
            self.logger.debug(f"executing script {remote_script_path} with an exit code of {ret_code}")
        self.logger.debug(f"finish script: {remote_script_path}")

        # step 3. pull files from remote SUT for following analyzing
        self.__pull_remote()
        
        return ret_code

    def __generate_script(self, script: str) -> str:
        """
        Generate a profiling script on SUT. 
        :param `script`: the string of shell script
        :return: path of the script on the SUT
        """
        remote_script_path = os.path.join(self.remote_tmp_dir, "perf.sh")
        with self.sftp.open(remote_script_path, "w") as f:
            f.write(script)
        self.logger.debug(f"generate script in remote temporary directory: {remote_script_path}")
        return remote_script_path

    def __pull_remote(self):
        """
        Pull all files to the test directory (a sub-directory in local temporary directory) from remote temporary directory.
        """
        for file in self.sftp.listdir(self.remote_tmp_dir):
            remote_file_path = os.path.join(self.remote_tmp_dir, file)
            self.sftp.get(remote_file_path, os.path.join(self.get_test_dir_path(), file))
            self.logger.debug(f"get file from remote SUT: {remote_file_path}")