# TerminateInstance200Response


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**data** | [**TerminateInstance200ResponseData**](TerminateInstance200ResponseData.md) |  | 

## Example

```python
from openapi_client.models.terminate_instance200_response import TerminateInstance200Response

# TODO update the JSON string below
json = "{}"
# create an instance of TerminateInstance200Response from a JSON string
terminate_instance200_response_instance = TerminateInstance200Response.from_json(json)
# print the JSON string representation of the object
print(TerminateInstance200Response.to_json())

# convert the object into a dict
terminate_instance200_response_dict = terminate_instance200_response_instance.to_dict()
# create an instance of TerminateInstance200Response from a dict
terminate_instance200_response_from_dict = TerminateInstance200Response.from_dict(terminate_instance200_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


