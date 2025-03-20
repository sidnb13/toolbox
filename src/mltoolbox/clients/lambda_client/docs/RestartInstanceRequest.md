# RestartInstanceRequest


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**instance_ids** | **List[str]** | The unique identifiers (IDs) of the instances to restart | 

## Example

```python
from openapi_client.models.restart_instance_request import RestartInstanceRequest

# TODO update the JSON string below
json = "{}"
# create an instance of RestartInstanceRequest from a JSON string
restart_instance_request_instance = RestartInstanceRequest.from_json(json)
# print the JSON string representation of the object
print(RestartInstanceRequest.to_json())

# convert the object into a dict
restart_instance_request_dict = restart_instance_request_instance.to_dict()
# create an instance of RestartInstanceRequest from a dict
restart_instance_request_from_dict = RestartInstanceRequest.from_dict(restart_instance_request_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


