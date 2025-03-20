# LaunchInstanceRequest


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**region_name** | **str** | Short name of a region | 
**instance_type_name** | **str** | Name of an instance type | 
**ssh_key_names** | **List[str]** | Names of the SSH keys to allow access to the instances. Currently, exactly one SSH key must be specified. | 
**file_system_names** | **List[str]** | Names of the file systems to attach to the instances. Currently, only one (if any) file system may be specified. | [optional] 
**quantity** | **int** | Number of instances to launch | [optional] [default to 1]
**name** | **str** | User-provided name for the instance | [optional] 

## Example

```python
from openapi_client.models.launch_instance_request import LaunchInstanceRequest

# TODO update the JSON string below
json = "{}"
# create an instance of LaunchInstanceRequest from a JSON string
launch_instance_request_instance = LaunchInstanceRequest.from_json(json)
# print the JSON string representation of the object
print(LaunchInstanceRequest.to_json())

# convert the object into a dict
launch_instance_request_dict = launch_instance_request_instance.to_dict()
# create an instance of LaunchInstanceRequest from a dict
launch_instance_request_from_dict = LaunchInstanceRequest.from_dict(launch_instance_request_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


