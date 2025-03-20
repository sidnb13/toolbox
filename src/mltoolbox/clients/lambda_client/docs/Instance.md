# Instance

Virtual machine (VM) in Lambda Cloud

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** | Unique identifier (ID) of an instance | 
**name** | **str** | User-provided name for the instance | [optional] 
**ip** | **str** | IPv4 address of the instance | [optional] 
**private_ip** | **str** | Private IPv4 address of the instance | [optional] 
**status** | **str** | The current status of the instance | 
**ssh_key_names** | **List[str]** | Names of the SSH keys allowed to access the instance | 
**file_system_names** | **List[str]** | Names of the file systems, if any, attached to the instance | 
**region** | [**Region**](Region.md) |  | [optional] 
**instance_type** | [**InstanceType**](InstanceType.md) |  | [optional] 
**hostname** | **str** | Hostname assigned to this instance, which resolves to the instance&#39;s IP. | [optional] 
**jupyter_token** | **str** | Secret token used to log into the jupyter lab server hosted on the instance. | [optional] 
**jupyter_url** | **str** | URL that opens a jupyter lab notebook on the instance. | [optional] 
**is_reserved** | **bool** | Whether the instance is reserved. | [optional] 

## Example

```python
from openapi_client.models.instance import Instance

# TODO update the JSON string below
json = "{}"
# create an instance of Instance from a JSON string
instance_instance = Instance.from_json(json)
# print the JSON string representation of the object
print(Instance.to_json())

# convert the object into a dict
instance_dict = instance_instance.to_dict()
# create an instance of Instance from a dict
instance_from_dict = Instance.from_dict(instance_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


