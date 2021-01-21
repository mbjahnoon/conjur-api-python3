"""
extend the unitest TestCase class
"""
# Builtins
import io
import sys
import concurrent.futures
# Third party
import itertools
from unittest import TestCase
from contextlib import redirect_stdout
import subprocess as sp
from unittest.mock import patch, MagicMock
# Internals
from conjur.cli import Cli
from test.util.test_runners.params import ClientParams, TestEnvironmentParams
from Utils import py_utils
class IntegrationTestCaseBase(TestCase):
    def __init__(self, testname, client_params: ClientParams = None,
                 environment_params: TestEnvironmentParams = None):
        """
        Base class that extends unittest TestCase
        used to setup tests environment
        """
        self.environment = TestEnvironmentParams() if environment_params is None else environment_params
        self.client_params = ClientParams() if client_params is None else client_params
        super(IntegrationTestCaseBase, self).__init__(testname)
    def invoke_cli(self, *args, exit_code=0) -> str:
        """
        Invoker for the integration tests.
        if self.environment.invoke_process == True
        than it will call the cli binaries to run the integration tests
        else it will use the Cli code to invoke
        """
        if self.environment.invoke_process:
            return invoke_cli_as_process(self, *args, exit_code=exit_code)
        return invoke_cli_as_code(self, *args, exit_code=exit_code)
def invoke_cli_as_code(test_runner, *args, exit_code=0):
    """
        Invoke cli command using python code as seen below.
        The usecase of this is when we run the tests
        on development environment (when you run from
        python ide or run this file as python script)
        @param test_runner:
        @param args: the cli args input
        @param exit_code:
        @return: the cli string response
        """
    capture_stream = io.StringIO()
    cli_args = list(itertools.chain(*args))
    with test_runner.assertRaises(SystemExit) as sys_exit:
        with redirect_stdout(capture_stream):
            with patch.object(sys, 'argv', ["cli"] + cli_args):
                Cli().run()
    test_runner.assertEqual(sys_exit.exception.code, exit_code,
                            "ERROR: CLI returned an unexpected error status code: '{}'".format(cli_args))
    return capture_stream.getvalue()
def invoke_cli_as_process(test_runner, *args, exit_code=0) -> str:
    """
    Invoke cli command using cli executable.
    The usecase of this is when we run the tests
    on test environment. will help tests integration
    on Windows, macOS, RHEL.
    This function is raising a conjur process with
    the test arguments. interactive inputs are passed
    to the conjur process using the process.stdin.write
    method. we get the interactive input for that from
    "unittest.patch" module defined in the integration
    tests code. This is not a straightforward operation.
    And you will notice two arguments in the code.
    1) max_interactions - > we limit the number of
    intercative command as the "patch" module can
    sometimes interact infinite number of times example:
        @patch('builtins.input', return_value='yes')
    2) interactive_input - raise a prompt withe a timeout
    to initiate interaction with "patch" and retrieve the
    desired value. note that the timeout is important in
    case no input will come from "patch".
    @param test_runner:
    @param args: the cli args input
    @param exit_code:
    @return: the cli string response
    """
    MAX_INTERACTIONS_ALLOWED = 5
    cli_args = list(itertools.chain(*args))
    run_cli_cmd = f"{test_runner.environment.cli_to_test}"
    with sp.Popen([run_cli_cmd] + cli_args, stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.STDOUT) as process:
        try:
            # number of max interactions allowed
            max_interactions = MAX_INTERACTIONS_ALLOWED
            while process.poll() is None and max_interactions > 0:
                max_interactions -= 1
                # timeout must be integer and should be the maximum seconds
                # waiting for the conjurCli to process an input
                interactive_input = get_input_if_exist(timeout=1)
                if interactive_input:
                    # pass the interactive input into conjurCli process
                    process.stdin.write(interactive_input)
                else:
                    break
        except Exception as e:
            print(e)
        output = process.communicate(timeout=30)[0]
        process_exit_code = process.returncode
        test_runner.assertEqual(process_exit_code, exit_code,
                                "ERROR: CLI returned an unexpected error status code: '{}'".format(cli_args))
    return output.decode('utf-8')
def get_input_if_exist(timeout=0.1):
    # get the input from the "unittest.patch"
    def get_input():
        try:
            data = input()
            return data
        except:
            # timeout
            return
    try:
        sys_in = py_utils.run_func_with_timeout(timeout, get_input)
        if sys_in:
            return (sys_in + "\n").encode('utf-8')
        return None
    except:
        return None