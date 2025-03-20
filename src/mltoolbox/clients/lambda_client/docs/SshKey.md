# SshKey

Information about a stored SSH key, which can be used to access instances over SSH

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** | Unique identifier (ID) of an SSH key | 
**name** | **str** | Name of the SSH key | 
**public_key** | **str** | Public key for the SSH key | 
**private_key** | **str** | Private key for the SSH key. Only returned when generating a new key pair. | [optional] 

## Example

```python
from openapi_client.models.ssh_key import SshKey

# TODO update the JSON string below
json = "{}"
# create an instance of SshKey from a JSON string
ssh_key_instance = SshKey.from_json(json)
# print the JSON string representation of the object
print(SshKey.to_json())

# convert the object into a dict
ssh_key_dict = ssh_key_instance.to_dict()
# create an instance of SshKey from a dict
ssh_key_from_dict = SshKey.from_dict(ssh_key_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


