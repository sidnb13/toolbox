# RestartInstance200Response


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**data** | [**RestartInstance200ResponseData**](RestartInstance200ResponseData.md) |  | 

## Example

```python
from openapi_client.models.restart_instance200_response import RestartInstance200Response

# TODO update the JSON string below
json = "{}"
# create an instance of RestartInstance200Response from a JSON string
restart_instance200_response_instance = RestartInstance200Response.from_json(json)
# print the JSON string representation of the object
print(RestartInstance200Response.to_json())

# convert the object into a dict
restart_instance200_response_dict = restart_instance200_response_instance.to_dict()
# create an instance of RestartInstance200Response from a dict
restart_instance200_response_from_dict = RestartInstance200Response.from_dict(restart_instance200_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


