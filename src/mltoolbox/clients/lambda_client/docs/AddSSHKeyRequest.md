# AddSSHKeyRequest

The name for the SSH key. Optionally, an existing public key can be supplied for the `public_key` property. If the `public_key` property is omitted, a new key pair is generated. The private key is returned in the response.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**name** | **str** | Name of the SSH key | 
**public_key** | **str** | Public key for the SSH key | [optional] 

## Example

```python
from openapi_client.models.add_ssh_key_request import AddSSHKeyRequest

# TODO update the JSON string below
json = "{}"
# create an instance of AddSSHKeyRequest from a JSON string
add_ssh_key_request_instance = AddSSHKeyRequest.from_json(json)
# print the JSON string representation of the object
print(AddSSHKeyRequest.to_json())

# convert the object into a dict
add_ssh_key_request_dict = add_ssh_key_request_instance.to_dict()
# create an instance of AddSSHKeyRequest from a dict
add_ssh_key_request_from_dict = AddSSHKeyRequest.from_dict(add_ssh_key_request_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


