# coding: utf-8

"""
    Lambda Cloud API

    API for interacting with the Lambda GPU Cloud

    The version of the OpenAPI document: 1.5.3
    Generated by OpenAPI Generator (https://openapi-generator.tech)

    Do not edit the class manually.
"""  # noqa: E501


import unittest

from openapi_client.models.add_ssh_key200_response import AddSSHKey200Response

class TestAddSSHKey200Response(unittest.TestCase):
    """AddSSHKey200Response unit test stubs"""

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def make_instance(self, include_optional) -> AddSSHKey200Response:
        """Test AddSSHKey200Response
            include_optional is a boolean, when False only required
            params are included, when True both required and
            optional params are included """
        # uncomment below to create an instance of `AddSSHKey200Response`
        """
        model = AddSSHKey200Response()
        if include_optional:
            return AddSSHKey200Response(
                data = openapi_client.models.ssh_key.sshKey(
                    id = '0920582c7ff041399e34823a0be62548', 
                    name = 'macbook-pro', 
                    public_key = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDfKpav4ILY54InZe27G user', 
                    private_key = '-----BEGIN RSA PRIVATE KEY-----
MIIEpQIBAAKCAQEA5IGybv8/wdQM6Y4yYTGiEem4TscBZiAW+9xyW2pDt8S7VDtm
...
eCW4938W9u8N3R/kpGwi1tZYiGMLBU4Ks0qKFi/VeEaE9OLeP5WQ8Pk=
-----END RSA PRIVATE KEY-----
', )
            )
        else:
            return AddSSHKey200Response(
                data = openapi_client.models.ssh_key.sshKey(
                    id = '0920582c7ff041399e34823a0be62548', 
                    name = 'macbook-pro', 
                    public_key = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDfKpav4ILY54InZe27G user', 
                    private_key = '-----BEGIN RSA PRIVATE KEY-----
MIIEpQIBAAKCAQEA5IGybv8/wdQM6Y4yYTGiEem4TscBZiAW+9xyW2pDt8S7VDtm
...
eCW4938W9u8N3R/kpGwi1tZYiGMLBU4Ks0qKFi/VeEaE9OLeP5WQ8Pk=
-----END RSA PRIVATE KEY-----
', ),
        )
        """

    def testAddSSHKey200Response(self):
        """Test AddSSHKey200Response"""
        # inst_req_only = self.make_instance(include_optional=False)
        # inst_req_and_optional = self.make_instance(include_optional=True)

if __name__ == '__main__':
    unittest.main()
