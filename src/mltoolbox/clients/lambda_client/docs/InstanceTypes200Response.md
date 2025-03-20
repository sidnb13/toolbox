# InstanceTypes200Response


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**data** | [**Dict[str, InstanceTypes200ResponseDataValue]**](InstanceTypes200ResponseDataValue.md) | Dict of instance_type_name to instance_type and region availability. | 

## Example

```python
from openapi_client.models.instance_types200_response import InstanceTypes200Response

# TODO update the JSON string below
json = "{}"
# create an instance of InstanceTypes200Response from a JSON string
instance_types200_response_instance = InstanceTypes200Response.from_json(json)
# print the JSON string representation of the object
print(InstanceTypes200Response.to_json())

# convert the object into a dict
instance_types200_response_dict = instance_types200_response_instance.to_dict()
# create an instance of InstanceTypes200Response from a dict
instance_types200_response_from_dict = InstanceTypes200Response.from_dict(instance_types200_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


