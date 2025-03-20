# RestartInstance200ResponseData


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**restarted_instances** | [**List[Instance]**](Instance.md) | List of instances that were restarted. Note: this list might not contain all instances requested to be restarted. | 

## Example

```python
from openapi_client.models.restart_instance200_response_data import RestartInstance200ResponseData

# TODO update the JSON string below
json = "{}"
# create an instance of RestartInstance200ResponseData from a JSON string
restart_instance200_response_data_instance = RestartInstance200ResponseData.from_json(json)
# print the JSON string representation of the object
print(RestartInstance200ResponseData.to_json())

# convert the object into a dict
restart_instance200_response_data_dict = restart_instance200_response_data_instance.to_dict()
# create an instance of RestartInstance200ResponseData from a dict
restart_instance200_response_data_from_dict = RestartInstance200ResponseData.from_dict(restart_instance200_response_data_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


