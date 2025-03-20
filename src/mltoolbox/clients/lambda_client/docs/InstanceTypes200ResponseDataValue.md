# InstanceTypes200ResponseDataValue


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**instance_type** | [**InstanceType**](InstanceType.md) |  | 
**regions_with_capacity_available** | [**List[Region]**](Region.md) | List of regions, if any, that have this instance type available | 

## Example

```python
from openapi_client.models.instance_types200_response_data_value import InstanceTypes200ResponseDataValue

# TODO update the JSON string below
json = "{}"
# create an instance of InstanceTypes200ResponseDataValue from a JSON string
instance_types200_response_data_value_instance = InstanceTypes200ResponseDataValue.from_json(json)
# print the JSON string representation of the object
print(InstanceTypes200ResponseDataValue.to_json())

# convert the object into a dict
instance_types200_response_data_value_dict = instance_types200_response_data_value_instance.to_dict()
# create an instance of InstanceTypes200ResponseDataValue from a dict
instance_types200_response_data_value_from_dict = InstanceTypes200ResponseDataValue.from_dict(instance_types200_response_data_value_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


