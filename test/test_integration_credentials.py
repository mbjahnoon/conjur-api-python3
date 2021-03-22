# -*- coding: utf-8 -*-

"""
CLI Integration Credentials tests

This test file handles the login/logout test flows when running
`conjur login`/`conjur logout`
"""
import os
import shutil
import string
from unittest.mock import patch
import uuid

from conjur.data_object import CredentialsData
from conjur.logic.credential_provider import CredentialStoreFactory, KeystoreCredentialsProvider
from test.util.test_infrastructure import integration_test
from test.util.test_runners.integration_test_case import IntegrationTestCaseBase
from test.util import test_helpers as utils

from conjur.constants import  DEFAULT_CONFIG_FILE, DEFAULT_CERTIFICATE_FILE,DEFAULT_NETRC_FILE


class CliIntegrationTestCredentials(IntegrationTestCaseBase):
    # *************** HELPERS ***************
    def __init__(self, testname, client_params=None, environment_params=None):
        super(CliIntegrationTestCredentials, self).__init__(testname, client_params, environment_params)

    def setup_cli_params(self, env_vars, *params):
        self.cli_auth_params = ['--debug']
        self.cli_auth_params += params

        return self.cli_auth_params

    def setUp(self):
        self.setup_cli_params({})
        try:
            utils.delete_credentials()
            utils.remove_file(DEFAULT_NETRC_FILE)
            utils.remove_file(DEFAULT_CONFIG_FILE)
            utils.remove_file(DEFAULT_CERTIFICATE_FILE)
        except OSError:
            pass
        utils.init_to_cli(self)

    def validate_credentials(self, machine, login, password):
        creds = utils.get_credentials()

        assert creds.machine == machine
        assert creds.login == login
        assert creds.password == password


    # *************** LOGIN CREDENTIALS TESTS ***************

    '''
    Validates that if a user configures the CLI in insecure mode and runs the command not in 
    insecure mode, then they will fail
    '''
    @integration_test(True)
    def test_cli_configured_in_insecure_mode_but_run_in_secure_mode_raises_error(self):
        shutil.copy(self.environment.path_provider.test_insecure_conjurrc_file_path, self.environment.path_provider.conjurrc_path)
        output = self.invoke_cli(self.cli_auth_params,
                            ['login', '-i', 'admin', '-p', self.client_params.env_api_key], exit_code=1)
        self.assertIn("The client was initialized without", output)

    '''
    Validates that if a user configures the CLI in insecure mode and runs a command in 
    insecure mode, then they will succeed
    '''
    @integration_test(True)
    @patch('builtins.input', return_value='yes')
    def test_cli_configured_in_insecure_mode_and_run_in_insecure_mode_passes(self, mock_input):
        self.invoke_cli(self.cli_auth_params,
                        ['--insecure', 'init', '--url', self.client_params.hostname, '--account', self.client_params.account])

        output = self.invoke_cli(self.cli_auth_params,
                            ['--insecure', 'login', '-i', 'admin', '-p', self.client_params.env_api_key])
        self.assertIn('Successfully logged in to Conjur', output)

    '''
    Validates a user can log in with a password, instead of their API key
    To do this, we perform the following:
    '''
    @integration_test()
    @patch('builtins.input', return_value='yes')
    def test_https_credentials_created_with_all_parameters_given(self, mock_input):
        self.invoke_cli(self.cli_auth_params,
                        ['login', '-i', 'admin', '-p', self.client_params.env_api_key])

        # Load in new user
        self.invoke_cli(self.cli_auth_params,
                        ['policy', 'replace', '-b', 'root', '-f', self.environment.path_provider.get_policy_path('conjur')])

        # Rotate the new user's API key
        user_api_key = self.invoke_cli(self.cli_auth_params,
                                       ['user', 'rotate-api-key', '-i', 'someuser'])
        extract_api_key_from_message = user_api_key.split(":")[1].strip()

        # Login to change personal password
        self.invoke_cli(self.cli_auth_params,
                        ['login', '-i', 'someuser', '-p', extract_api_key_from_message])

        # Creates a password that meets Conjur password complexity standards
        password = string.hexdigits + "$!@"
        self.invoke_cli(self.cli_auth_params,
                        ['user', 'change-password', '-p', password])

        self.invoke_cli(self.cli_auth_params,
                        ['logout'])

        # Attempt to login with newly created password
        output = self.invoke_cli(self.cli_auth_params,
                        ['login', '-i', 'someuser', '-p', password])

        self.assertIn("Successfully logged in to Conjur", output.strip())
        utils.get_credentials()
        self.validate_credentials(f"{self.client_params.hostname}", "someuser", extract_api_key_from_message)

    '''
    Validates a wrong username will raise Unauthorized error
    '''
    @integration_test()
    @patch('builtins.input', return_value='somebaduser')
    def test_https_credentials_raises_error_with_wrong_user(self, mock_pass):
        with patch('getpass.getpass', return_value=self.client_params.env_api_key):
            output = self.invoke_cli(self.cli_auth_params,
                                     ['login'], exit_code=1)

            self.assertRegex(output, "Reason: 401")

    '''
    Validates a wrong password will raise Unauthorized error
    '''
    @integration_test()
    @patch('builtins.input', return_value='admin')
    @patch('getpass.getpass', return_value='somewrongpass')
    def test_https_credentials_with_wrong_password(self, mock_pass, mock_input):

        output = self.invoke_cli(self.cli_auth_params,
                                 ['login'], exit_code=1)

        self.assertRegex(output, "Reason: 401")






    '''
    Validates that when the user hasn't logged in and attempts 
    to run a command, they will be prompted to login
    '''
    @integration_test()
    @patch('builtins.input', return_value='someaccount')
    @patch('getpass.getpass', return_value='somepass')
    def test_user_runs_list_without_credentials_prompts_user_to_login(self, mock_pass, mock_input):
        # Set this environment variable to prompt the user to login
        os.environ["TEST_ENV"] = "False"
        list_attempt = self.invoke_cli(self.cli_auth_params,
                                       ['list'], exit_code=1)
        self.assertRegex(list_attempt.strip(), "Unable to authenticate with Conjur.")
        os.environ["TEST_ENV"] = "True"

    @integration_test()
    @patch('builtins.input', return_value='admin')
    def test_https_credentials_is_created_when_provided_user_api_key(self, mock_pass):
        with patch('getpass.getpass', return_value=self.client_params.env_api_key):
            output = self.invoke_cli(self.cli_auth_params,
                                     ['login'])

            assert utils.get_credentials() is not None
            self.assertIn("Successfully logged in to Conjur", output.strip())

            self.validate_credentials(f"{self.client_params.hostname}", "admin", self.client_params.env_api_key)

    '''
        Validates interactively provided params create credentials
        '''

    @integration_test()
    @patch('builtins.input', return_value='admin')
    def test_https_credentials_is_created_with_all_parameters_given_interactively(self, mock_pass):
        with patch('getpass.getpass', return_value=self.client_params.env_api_key):
            output = self.invoke_cli(self.cli_auth_params, ['login'])

            assert utils.get_credentials() is not None
            self.assertIn("Successfully logged in to Conjur", output.strip())
            self.validate_credentials(f"{self.client_params.hostname}", "admin", self.client_params.env_api_key)

    '''
        Validates login is successful for hosts

        Note we need to create the host first and rotate it's API key so that we can access it.
        There is currently no way to fetch a host's API key so this is a work around for the 
        purposes of this test
        '''

    @integration_test()
    def test_https_credentials_is_created_with_host(self):
        # Setup for fetching the API key of a host. To fetch we need to login
        credentials = CredentialsData(self.client_params.hostname,"admin",self.client_params.env_api_key)
        utils.save_credentials(credentials)

        self.invoke_cli(self.cli_auth_params,
                        ['policy', 'replace', '-b', 'root', '-f',
                         self.environment.path_provider.get_policy_path('conjur')])

        host_api_key = self.invoke_cli(self.cli_auth_params,
                                       ['host', 'rotate-api-key', '-i', 'somehost'])

        extract_api_key_from_message = host_api_key.split(":")[1].strip()

        self.invoke_cli(self.cli_auth_params,
                        ['logout'])

        output = self.invoke_cli(self.cli_auth_params,
                                 ['login', '-i', 'host/somehost', '-p', f'{extract_api_key_from_message}'])

        self.validate_credentials(f"{self.client_params.hostname}", "host/somehost", extract_api_key_from_message)
        self.assertIn("Successfully logged in to Conjur", output.strip())

    @integration_test()
    def test_working_with_keystore(self):
        cred_store,_ = CredentialStoreFactory().create_credential_store()
        self.assertEquals(type(cred_store) , type(KeystoreCredentialsProvider()))

    '''
        Validates logout doesn't remove another entry not associated with Cyberark
        '''

    @integration_test(True)
    def test_https_credentials_does_not_remove_irrelevant_entry(self):
        creds = CredentialsData(self.client_params.hostname,"admin",self.client_params.env_api_key)
        utils.save_credentials(creds)

        creds = CredentialsData("somemachine", "somelogin", "somepass")
        utils.save_credentials(creds)

        self.invoke_cli(self.cli_auth_params,
                        ['logout'])
        cred_store, _ = CredentialStoreFactory().create_credential_store()
        assert cred_store.is_exists("somemachine")
        assert not cred_store.is_exists(self.client_params.hostname)

    @integration_test(True)
    def test_https_logout_twice_returns_could_not_logout_message(self):

        self.invoke_cli(self.cli_auth_params,
                        ['login', '-i', 'admin', '-p', self.client_params.env_api_key])

        self.invoke_cli(self.cli_auth_params,
                        ['logout'])

        unsuccessful_logout = self.invoke_cli(self.cli_auth_params,
                                              ['logout'], exit_code=1)

        self.assertIn("Failed to log out. You are already logged out", unsuccessful_logout.strip())

    '''
        Validates when a user can logout successfully
    '''

    @integration_test(True)
    def test_https_logout_successful(self):

        self.invoke_cli(self.cli_auth_params,
                        ['login', '-i', 'admin', '-p', self.client_params.env_api_key])

        output = self.invoke_cli(self.cli_auth_params,
                                 ['logout'])

        self.assertIn('Successfully logged out from Conjur', output.strip())

    '''
        Validates that if a user configures the CLI in insecure mode and runs the command not in 
        insecure mode, then they will fail
    '''

    @integration_test(True)
    def test_cli_configured_in_insecure_mode_but_run_in_secure_mode_raises_error(self):
        shutil.copy(self.environment.path_provider.test_insecure_conjurrc_file_path,
                    self.environment.path_provider.conjurrc_path)
        output = self.invoke_cli(self.cli_auth_params,
                                 ['login', '-i', 'admin', '-p', self.client_params.env_api_key], exit_code=1)
        self.assertIn("The client was initialized without", output)


    @integration_test(True)
    def test_https_logout_successful(self):
        utils.setup_cli(self)
        self.invoke_cli(self.cli_auth_params,
                        ['login', '-i', 'admin', '-p', self.client_params.env_api_key])

        output = self.invoke_cli(self.cli_auth_params,
                                 ['logout'])

        self.assertIn('Successfully logged out from Conjur', output.strip())

    '''
        Validates that if a user configures the CLI in insecure mode and runs the command not in 
        insecure mode, then they will fail
    '''

    @integration_test(True)
    def test_cli_configured_in_insecure_mode_but_run_in_secure_mode_raises_error(self):
        shutil.copy(self.environment.path_provider.test_insecure_conjurrc_file_path,
                    self.environment.path_provider.conjurrc_path)
        output = self.invoke_cli(self.cli_auth_params,
                                 ['login', '-i', 'admin', '-p', self.client_params.env_api_key], exit_code=1)
        self.assertIn("The client was initialized without", output)

    @integration_test()
    def test_simple_login(self):
        utils.setup_cli(self)
        creds = utils.get_credentials()
        assert creds.machine == self.client_params.hostname
        self.invoke_cli(self.cli_auth_params,['logout'])
        assert not utils.is_credentials_exist(creds.machine)
        self.invoke_cli(self.cli_auth_params, ['list'],exit_code=1)

    @integration_test(True)
    def test_https_can_load_policy(self):
        self.setup_cli_params({})
        utils.setup_cli(self)
        policy, variables = utils.generate_policy_string(self)
        utils.load_policy_from_string(self, policy)

        for variable in variables:
            utils.assert_set_and_get(self, variable)

    @integration_test(True)
    def test_keyring_locked_in_the_middle(self):
        utils.setup_cli(self)
        with patch('conjur.wrapper.keystore_adapter.KeystoreAdapter.is_keyring_accessible', return_value=False):
            self.invoke_cli(self.cli_auth_params, ['logout'],exit_code=1)

    @integration_test()
    def test_secret(self):
        """
        Note about version tests, the Conjur server only keeps a certain number of versions.
        With each run of the integration tests, version tests are resetting variable values
        making, after a certain number of runs, version=1 not valid and fail
        Therefore, the variable name needs to be a random string so that the version
        will still be accessible
        """
        utils.setup_cli(self)
        variable_name = "someversionedvar" + uuid.uuid4().hex
        policy = f"- !variable {variable_name}"
        utils.load_policy_from_string(self, policy)

        expected_value = "anothersecret"
        utils.set_variable(self, variable_name, expected_value)
        output = self.invoke_cli(self.cli_auth_params,
                                 ['variable', 'get', '-i', variable_name, '--version', '1'])
        self.assertIn(expected_value, output.strip())
