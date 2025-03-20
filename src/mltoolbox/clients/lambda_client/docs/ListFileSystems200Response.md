# ListFileSystems200Response


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**data** | [**List[FileSystem]**](FileSystem.md) |  | 

## Example

```python
from openapi_client.models.list_file_systems200_response import ListFileSystems200Response

# TODO update the JSON string below
json = "{}"
# create an instance of ListFileSystems200Response from a JSON string
list_file_systems200_response_instance = ListFileSystems200Response.from_json(json)
# print the JSON string representation of the object
print(ListFileSystems200Response.to_json())

# convert the object into a dict
list_file_systems200_response_dict = list_file_systems200_response_instance.to_dict()
# create an instance of ListFileSystems200Response from a dict
list_file_systems200_response_from_dict = ListFileSystems200Response.from_dict(list_file_systems200_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


