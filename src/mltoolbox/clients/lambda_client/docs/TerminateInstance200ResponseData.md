# TerminateInstance200ResponseData


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**terminated_instances** | [**List[Instance]**](Instance.md) | List of instances that were terminated. Note: this list might not contain all instances requested to be terminated. | 

## Example

```python
from openapi_client.models.terminate_instance200_response_data import TerminateInstance200ResponseData

# TODO update the JSON string below
json = "{}"
# create an instance of TerminateInstance200ResponseData from a JSON string
terminate_instance200_response_data_instance = TerminateInstance200ResponseData.from_json(json)
# print the JSON string representation of the object
print(TerminateInstance200ResponseData.to_json())

# convert the object into a dict
terminate_instance200_response_data_dict = terminate_instance200_response_data_instance.to_dict()
# create an instance of TerminateInstance200ResponseData from a dict
terminate_instance200_response_data_from_dict = TerminateInstance200ResponseData.from_dict(terminate_instance200_response_data_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


