# TerminateInstanceRequest


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**instance_ids** | **List[str]** | The unique identifiers (IDs) of the instances to terminate | 

## Example

```python
from openapi_client.models.terminate_instance_request import TerminateInstanceRequest

# TODO update the JSON string below
json = "{}"
# create an instance of TerminateInstanceRequest from a JSON string
terminate_instance_request_instance = TerminateInstanceRequest.from_json(json)
# print the JSON string representation of the object
print(TerminateInstanceRequest.to_json())

# convert the object into a dict
terminate_instance_request_dict = terminate_instance_request_instance.to_dict()
# create an instance of TerminateInstanceRequest from a dict
terminate_instance_request_from_dict = TerminateInstanceRequest.from_dict(terminate_instance_request_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


