from argparse import ArgumentParser, REMAINDER
from typing import Sequence
import logging
from getpass import getpass


class OptParser:
    """
    'OptParser' is responsible for parsing arguments passed from command line and instantiate Task, Profiler and Connector
    """

    def __init__(self) -> None:
        """
        Constructor of 'OptParser'
        """
        self.parser = ArgumentParser(prog="python hperf.py",
                                     description="hperf: an easy-to-use microarchitecture performance data collector")

        # positional arguments:
        # COMMAND
        self.parser.add_argument("command",
                                 # if option 'nargs' not set, command with arguments will not be accepted.
                                 nargs=REMAINDER,
                                 metavar="COMMAND",
                                 help="workload command you can specify in a shell")

        # required options:
        # TODO: some required options can be added in future

        # optional options:
        # [-r/--remote SSH_CONN_STR]
        self.parser.add_argument("-r", "--remote",
                                 metavar="SSH_CONN_STR",
                                 type=str,
                                 help="profiling on remote host by specifying a SSH connection string (default on local host).")
        # [--tmp-dir]
        self.parser.add_argument("--tmp-dir",
                                 metavar="TMP_DIR_PATH",
                                 type=str,
                                 default="/tmp/hperf/",
                                 help="temporary directory to store profiling results and logs (default '/tmp/hperf/').")
        # [-v/--verbose]
        self.parser.add_argument("-v", "--verbose",
                                 action="store_true",
                                 help="increase output verbosity.")

        # [--cpu CPU]
        # hperf will conduct a system-wide profiling so that the list will not affect performance data collection
        # but will affect the aggregation of raw performance data.
        # If not specified, 'Analyzer' will aggregate performance data of all cpus.
        self.parser.add_argument("-c", "--cpu",
                                 metavar="CPU_ID_LIST",
                                 type=str,
                                 default="all",
                                 help="specify the scope of performance data aggregation by passing a list of cpu ids.")

        # TODO: add more options in future
        # [--config FILE_PATH]
        # self.parser.add_argument("-f", "--config-file",
        #                          metavar="FILE_PATH",
        #                          type=str,
        #                          help="specify a configuration file with JSON format.")
        # [--time SECOND]
        # current workaround: COMMAND = sleep n
        # self.parser.add_argument("-t", "--time",
        #                          metavar="SECOND",
        #                          type=int,
        #                          help="time of profiling (s).")

    def parse_args(self, argv: Sequence[str]) -> dict:
        """
        Parse the options and parameters passed from command line and return an instance of Connector
        :param argv: a list of arguments
        :return configs: configure of this hperf run
        """
        configs = {}

        args = self.parser.parse_args(argv)
        # TODO: for future implementation: if -f/--config-file option is specified,
        # load the JSON file and initialize config dict
        # if args.config:
        #     with open(args.config) as f:
        #         configs.update(json.load(f))
        # parse other options and arguments and update config dict
        # config specified in command line will overwrite the config defined in JSON file

        # step 0. check verbosity
        if args.verbose:
            # option 'force' is needed, otherwise the level will not changed.
            logging.basicConfig(
                format="%(asctime)-15s %(levelname)-8s %(message)s", level=logging.DEBUG, force=True)

        logging.debug(
            f"options and arguments passed from command line: {args}")

        # step 1. workload command
        if args.command:
            configs["command"] = " ".join(args.command)

        # step 2. local / remote SUT (default local)
        if args.remote:
            configs["host_type"] = "remote"
            remote_configs = self.__parse_remote_str(args.remote)
            # add keys: hostname, username, password
            configs.update(remote_configs)
        else:
            configs["host_type"] = "local"

        # step 3. scope of performance data aggregation
        if args.cpu != "all":
            configs["cpu_list"] = self.__parse_cpu_list(args.cpu)
        else:
            configs["cpu_list"] = "all"

        # step 4. temporary directory
        if args.tmp_dir:
            configs["tmp_dir"] = args.tmp_dir

        logging.debug(f"parsed configurations: {configs}")

        return configs

    def __parse_cpu_list(self, cpu_list: str) -> list:
        """
        Parse the cpu list string with comma (,) and hyphen (-), and get the list of cpu ids.
        e.g. if cpu_list = '2,4-8', the method will return [2, 4, 5, 6, 7, 8]
        """
        cpu_ids = []
        cpu_id_slices = cpu_list.split(",")
        try:
            for item in cpu_id_slices:
                if item.find("-") == -1:
                    cpu_ids.append(int(item))
                else:
                    start_cpu_id = int(item.split("-")[0])
                    end_cpu_id = int(item.split("-")[1])
                    for i in range(start_cpu_id, end_cpu_id + 1):
                        cpu_ids.append(i)
        except ValueError:
            logging.error(f"invalid argument {cpu_list} for -c/--cpu option")
            exit(-1)
        reduced_cpu_ids = list(set(cpu_ids))
        reduced_cpu_ids.sort(key=cpu_ids.index)
        
        # check if all cpu ids are vaild (not negative)
        for cpu_id in reduced_cpu_ids:
            if cpu_id < 0:
                logging.error(f"invalid argument {cpu_list} for -c/--cpu option")
                exit(-1)
        return reduced_cpu_ids

    def __parse_remote_str(self, ssh_conn_str: str) -> dict:
        """
        Parse the SSH connection string with the format of 'username@hostname', then ask user to enter the password.
        :param ssh_conn_str: SSH connection string
        :return: a dict of remote host informations
        """
        # TODO: try to parse all information for the remote SSH connection from the parameter of -r / --remote option.
        # e.g. ssh_conn_str = "tongyu@ampere.solelab.tech"

        remote_configs = {}
        # parse the SSH connection string to get hostname and username
        try:
            # TODO: enhance the logic of parsing SSH connection string
            remote_configs["username"]: str = ssh_conn_str.split("@")[0]
            remote_configs["hostname"]: str = ssh_conn_str.split("@")[1]
            if remote_configs["username"] == "" or remote_configs["hostname"] == "":
                raise ValueError
        except (IndexError, ValueError):
            logging.error(f"invalid SSH connection string: {ssh_conn_str}")
            exit(-1)

        # get the password by command line interaction
        remote_configs["password"] = getpass(f'connect to {remote_configs["hostname"]}, '
                                             f'enter the password for user {remote_configs["username"]}: ')

        # TODO: other configurations may be used in future
        # remote_configs["port"] = 22
        # remote_configs["private_key"] = "~/.ssh/id_rsa"

        return remote_configs
