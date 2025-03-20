# InstanceTypeSpecs


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**vcpus** | **int** | Number of virtual CPUs | 
**memory_gib** | **int** | Amount of RAM, in gibibytes (GiB) | 
**storage_gib** | **int** | Amount of storage, in gibibytes (GiB). | 
**gpus** | **int** | Number of GPUs | 

## Example

```python
from openapi_client.models.instance_type_specs import InstanceTypeSpecs

# TODO update the JSON string below
json = "{}"
# create an instance of InstanceTypeSpecs from a JSON string
instance_type_specs_instance = InstanceTypeSpecs.from_json(json)
# print the JSON string representation of the object
print(InstanceTypeSpecs.to_json())

# convert the object into a dict
instance_type_specs_dict = instance_type_specs_instance.to_dict()
# create an instance of InstanceTypeSpecs from a dict
instance_type_specs_from_dict = InstanceTypeSpecs.from_dict(instance_type_specs_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


