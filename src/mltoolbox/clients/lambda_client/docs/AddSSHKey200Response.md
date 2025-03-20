# AddSSHKey200Response

The added or generated SSH public key. If a new key pair was generated, the response body contains a `private_key` property that *must* be saved locally. Lambda Cloud does not store private keys.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**data** | [**SshKey**](SshKey.md) |  | 

## Example

```python
from openapi_client.models.add_ssh_key200_response import AddSSHKey200Response

# TODO update the JSON string below
json = "{}"
# create an instance of AddSSHKey200Response from a JSON string
add_ssh_key200_response_instance = AddSSHKey200Response.from_json(json)
# print the JSON string representation of the object
print(AddSSHKey200Response.to_json())

# convert the object into a dict
add_ssh_key200_response_dict = add_ssh_key200_response_instance.to_dict()
# create an instance of AddSSHKey200Response from a dict
add_ssh_key200_response_from_dict = AddSSHKey200Response.from_dict(add_ssh_key200_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


