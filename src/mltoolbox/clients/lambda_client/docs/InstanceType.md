# InstanceType

Hardware configuration and pricing of an instance type

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**name** | **str** | Name of an instance type | 
**description** | **str** | Long name of the instance type | 
**gpu_description** | **str** | Description of the GPU(s) in the instance type | 
**price_cents_per_hour** | **int** | Price of the instance type, in US cents per hour | 
**specs** | [**InstanceTypeSpecs**](InstanceTypeSpecs.md) |  | 

## Example

```python
from openapi_client.models.instance_type import InstanceType

# TODO update the JSON string below
json = "{}"
# create an instance of InstanceType from a JSON string
instance_type_instance = InstanceType.from_json(json)
# print the JSON string representation of the object
print(InstanceType.to_json())

# convert the object into a dict
instance_type_dict = instance_type_instance.to_dict()
# create an instance of InstanceType from a dict
instance_type_from_dict = InstanceType.from_dict(instance_type_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


