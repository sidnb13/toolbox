# FileSystem

Information about a shared file system

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** | Unique identifier (ID) of a file system | 
**name** | **str** | Name of a file system | 
**created** | **str** | A date and time, formatted as an ISO 8601 time stamp | 
**created_by** | [**User**](User.md) |  | 
**mount_point** | **str** | Absolute path indicating where on instances the file system will be mounted | 
**region** | [**Region**](Region.md) |  | 
**is_in_use** | **bool** | Whether the file system is currently in use by an instance. File systems that are in use cannot be deleted. | 
**bytes_used** | **int** | Approximate amount of storage used by the file system, in bytes. This value is an estimate that is updated every several hours. | [optional] 

## Example

```python
from openapi_client.models.file_system import FileSystem

# TODO update the JSON string below
json = "{}"
# create an instance of FileSystem from a JSON string
file_system_instance = FileSystem.from_json(json)
# print the JSON string representation of the object
print(FileSystem.to_json())

# convert the object into a dict
file_system_dict = file_system_instance.to_dict()
# create an instance of FileSystem from a dict
file_system_from_dict = FileSystem.from_dict(file_system_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


