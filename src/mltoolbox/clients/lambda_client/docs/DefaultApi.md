# openapi_client.DefaultApi

All URIs are relative to *https://cloud.lambdalabs.com/api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**add_ssh_key**](DefaultApi.md#add_ssh_key) | **POST** /ssh-keys | Add SSH key
[**delete_ssh_key**](DefaultApi.md#delete_ssh_key) | **DELETE** /ssh-keys/{id} | Delete SSH key
[**get_instance**](DefaultApi.md#get_instance) | **GET** /instances/{id} | List details of a specific instance
[**instance_types**](DefaultApi.md#instance_types) | **GET** /instance-types | Retrieve list of offered instance types
[**launch_instance**](DefaultApi.md#launch_instance) | **POST** /instance-operations/launch | Launch instances
[**list_file_systems**](DefaultApi.md#list_file_systems) | **GET** /file-systems | List file systems
[**list_instances**](DefaultApi.md#list_instances) | **GET** /instances | List running instances
[**list_ssh_keys**](DefaultApi.md#list_ssh_keys) | **GET** /ssh-keys | List SSH keys
[**restart_instance**](DefaultApi.md#restart_instance) | **POST** /instance-operations/restart | Restart instances
[**terminate_instance**](DefaultApi.md#terminate_instance) | **POST** /instance-operations/terminate | Terminate an instance


# **add_ssh_key**
> AddSSHKey200Response add_ssh_key(add_ssh_key_request)

Add SSH key

Add an SSH key  To use an existing key pair, enter the public key for the `public_key` property of the request body.  To generate a new key pair, omit the `public_key` property from the request body. Save the `private_key` from the response somewhere secure. For example, with curl:  ``` curl https://cloud.lambdalabs.com/api/v1/ssh-keys \\   --fail \\   -u ${LAMBDA_API_KEY}: \\   -X POST \\   -d '{\"name\": \"new key\"}' \\   | jq -r '.data.private_key' > key.pem  chmod 400 key.pem ```  Then, after you launch an instance with `new key` attached to it: ``` ssh -i key.pem <instance IP> ``` 

### Example

* Basic Authentication (basicAuth):
* Bearer (auth-scheme) Authentication (bearerAuth):

```python
import openapi_client
from openapi_client.models.add_ssh_key200_response import AddSSHKey200Response
from openapi_client.models.add_ssh_key_request import AddSSHKeyRequest
from openapi_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to https://cloud.lambdalabs.com/api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://cloud.lambdalabs.com/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = openapi_client.Configuration(
    username = os.environ["USERNAME"],
    password = os.environ["PASSWORD"]
)

# Configure Bearer authorization (auth-scheme): bearerAuth
configuration = openapi_client.Configuration(
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.DefaultApi(api_client)
    add_ssh_key_request = openapi_client.AddSSHKeyRequest() # AddSSHKeyRequest | 

    try:
        # Add SSH key
        api_response = api_instance.add_ssh_key(add_ssh_key_request)
        print("The response of DefaultApi->add_ssh_key:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling DefaultApi->add_ssh_key: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **add_ssh_key_request** | [**AddSSHKeyRequest**](AddSSHKeyRequest.md)|  | 

### Return type

[**AddSSHKey200Response**](AddSSHKey200Response.md)

### Authorization

[basicAuth](../README.md#basicAuth), [bearerAuth](../README.md#bearerAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**401** | Unauthorized. |  -  |
**403** | Forbidden. |  -  |
**400** | Request parameters were invalid. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **delete_ssh_key**
> delete_ssh_key(id)

Delete SSH key

Delete an SSH key.

### Example

* Basic Authentication (basicAuth):
* Bearer (auth-scheme) Authentication (bearerAuth):

```python
import openapi_client
from openapi_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to https://cloud.lambdalabs.com/api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://cloud.lambdalabs.com/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = openapi_client.Configuration(
    username = os.environ["USERNAME"],
    password = os.environ["PASSWORD"]
)

# Configure Bearer authorization (auth-scheme): bearerAuth
configuration = openapi_client.Configuration(
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.DefaultApi(api_client)
    id = 'id_example' # str | The unique identifier (ID) of the SSH key

    try:
        # Delete SSH key
        api_instance.delete_ssh_key(id)
    except Exception as e:
        print("Exception when calling DefaultApi->delete_ssh_key: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **str**| The unique identifier (ID) of the SSH key | 

### Return type

void (empty response body)

### Authorization

[basicAuth](../README.md#basicAuth), [bearerAuth](../README.md#bearerAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Deletion successful |  -  |
**400** | Request parameters were invalid. |  -  |
**401** | Unauthorized. |  -  |
**403** | Forbidden. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **get_instance**
> GetInstance200Response get_instance(id)

List details of a specific instance

Retrieves details of a specific instance, including whether or not the instance is running. 

### Example

* Basic Authentication (basicAuth):
* Bearer (auth-scheme) Authentication (bearerAuth):

```python
import openapi_client
from openapi_client.models.get_instance200_response import GetInstance200Response
from openapi_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to https://cloud.lambdalabs.com/api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://cloud.lambdalabs.com/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = openapi_client.Configuration(
    username = os.environ["USERNAME"],
    password = os.environ["PASSWORD"]
)

# Configure Bearer authorization (auth-scheme): bearerAuth
configuration = openapi_client.Configuration(
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.DefaultApi(api_client)
    id = 'id_example' # str | The unique identifier (ID) of the instance

    try:
        # List details of a specific instance
        api_response = api_instance.get_instance(id)
        print("The response of DefaultApi->get_instance:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling DefaultApi->get_instance: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **id** | **str**| The unique identifier (ID) of the instance | 

### Return type

[**GetInstance200Response**](GetInstance200Response.md)

### Authorization

[basicAuth](../README.md#basicAuth), [bearerAuth](../README.md#bearerAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**401** | Unauthorized. |  -  |
**403** | Forbidden. |  -  |
**404** | Object does not exist. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **instance_types**
> InstanceTypes200Response instance_types()

Retrieve list of offered instance types

Returns a detailed list of the instance types offered by Lambda GPU Cloud. The details include the regions, if any, in which each instance type is currently available. 

### Example

* Basic Authentication (basicAuth):
* Bearer (auth-scheme) Authentication (bearerAuth):

```python
import openapi_client
from openapi_client.models.instance_types200_response import InstanceTypes200Response
from openapi_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to https://cloud.lambdalabs.com/api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://cloud.lambdalabs.com/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = openapi_client.Configuration(
    username = os.environ["USERNAME"],
    password = os.environ["PASSWORD"]
)

# Configure Bearer authorization (auth-scheme): bearerAuth
configuration = openapi_client.Configuration(
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.DefaultApi(api_client)

    try:
        # Retrieve list of offered instance types
        api_response = api_instance.instance_types()
        print("The response of DefaultApi->instance_types:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling DefaultApi->instance_types: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**InstanceTypes200Response**](InstanceTypes200Response.md)

### Authorization

[basicAuth](../README.md#basicAuth), [bearerAuth](../README.md#bearerAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**401** | Unauthorized. |  -  |
**403** | Forbidden. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **launch_instance**
> LaunchInstance200Response launch_instance(launch_instance_request)

Launch instances

Launches one or more instances of a given instance type.

### Example

* Basic Authentication (basicAuth):
* Bearer (auth-scheme) Authentication (bearerAuth):

```python
import openapi_client
from openapi_client.models.launch_instance200_response import LaunchInstance200Response
from openapi_client.models.launch_instance_request import LaunchInstanceRequest
from openapi_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to https://cloud.lambdalabs.com/api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://cloud.lambdalabs.com/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = openapi_client.Configuration(
    username = os.environ["USERNAME"],
    password = os.environ["PASSWORD"]
)

# Configure Bearer authorization (auth-scheme): bearerAuth
configuration = openapi_client.Configuration(
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.DefaultApi(api_client)
    launch_instance_request = openapi_client.LaunchInstanceRequest() # LaunchInstanceRequest | 

    try:
        # Launch instances
        api_response = api_instance.launch_instance(launch_instance_request)
        print("The response of DefaultApi->launch_instance:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling DefaultApi->launch_instance: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **launch_instance_request** | [**LaunchInstanceRequest**](LaunchInstanceRequest.md)|  | 

### Return type

[**LaunchInstance200Response**](LaunchInstance200Response.md)

### Authorization

[basicAuth](../README.md#basicAuth), [bearerAuth](../README.md#bearerAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**401** | Unauthorized. |  -  |
**403** | Forbidden. |  -  |
**400** | Request parameters were invalid. |  -  |
**404** | Object does not exist. |  -  |
**500** | Something unexpected occurred. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_file_systems**
> ListFileSystems200Response list_file_systems()

List file systems

Retrieve the list of file systems

### Example

* Basic Authentication (basicAuth):
* Bearer (auth-scheme) Authentication (bearerAuth):

```python
import openapi_client
from openapi_client.models.list_file_systems200_response import ListFileSystems200Response
from openapi_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to https://cloud.lambdalabs.com/api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://cloud.lambdalabs.com/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = openapi_client.Configuration(
    username = os.environ["USERNAME"],
    password = os.environ["PASSWORD"]
)

# Configure Bearer authorization (auth-scheme): bearerAuth
configuration = openapi_client.Configuration(
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.DefaultApi(api_client)

    try:
        # List file systems
        api_response = api_instance.list_file_systems()
        print("The response of DefaultApi->list_file_systems:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling DefaultApi->list_file_systems: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**ListFileSystems200Response**](ListFileSystems200Response.md)

### Authorization

[basicAuth](../README.md#basicAuth), [bearerAuth](../README.md#bearerAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**401** | Unauthorized. |  -  |
**403** | Forbidden. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_instances**
> ListInstances200Response list_instances()

List running instances

Retrieves a detailed list of running instances.

### Example

* Basic Authentication (basicAuth):
* Bearer (auth-scheme) Authentication (bearerAuth):

```python
import openapi_client
from openapi_client.models.list_instances200_response import ListInstances200Response
from openapi_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to https://cloud.lambdalabs.com/api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://cloud.lambdalabs.com/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = openapi_client.Configuration(
    username = os.environ["USERNAME"],
    password = os.environ["PASSWORD"]
)

# Configure Bearer authorization (auth-scheme): bearerAuth
configuration = openapi_client.Configuration(
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.DefaultApi(api_client)

    try:
        # List running instances
        api_response = api_instance.list_instances()
        print("The response of DefaultApi->list_instances:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling DefaultApi->list_instances: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**ListInstances200Response**](ListInstances200Response.md)

### Authorization

[basicAuth](../README.md#basicAuth), [bearerAuth](../README.md#bearerAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**401** | Unauthorized. |  -  |
**403** | Forbidden. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_ssh_keys**
> ListSSHKeys200Response list_ssh_keys()

List SSH keys

Retrieve the list of SSH keys

### Example

* Basic Authentication (basicAuth):
* Bearer (auth-scheme) Authentication (bearerAuth):

```python
import openapi_client
from openapi_client.models.list_ssh_keys200_response import ListSSHKeys200Response
from openapi_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to https://cloud.lambdalabs.com/api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://cloud.lambdalabs.com/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = openapi_client.Configuration(
    username = os.environ["USERNAME"],
    password = os.environ["PASSWORD"]
)

# Configure Bearer authorization (auth-scheme): bearerAuth
configuration = openapi_client.Configuration(
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.DefaultApi(api_client)

    try:
        # List SSH keys
        api_response = api_instance.list_ssh_keys()
        print("The response of DefaultApi->list_ssh_keys:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling DefaultApi->list_ssh_keys: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**ListSSHKeys200Response**](ListSSHKeys200Response.md)

### Authorization

[basicAuth](../README.md#basicAuth), [bearerAuth](../README.md#bearerAuth)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**401** | Unauthorized. |  -  |
**403** | Forbidden. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **restart_instance**
> RestartInstance200Response restart_instance(restart_instance_request)

Restart instances

Restarts the given instances.

### Example

* Basic Authentication (basicAuth):
* Bearer (auth-scheme) Authentication (bearerAuth):

```python
import openapi_client
from openapi_client.models.restart_instance200_response import RestartInstance200Response
from openapi_client.models.restart_instance_request import RestartInstanceRequest
from openapi_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to https://cloud.lambdalabs.com/api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://cloud.lambdalabs.com/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = openapi_client.Configuration(
    username = os.environ["USERNAME"],
    password = os.environ["PASSWORD"]
)

# Configure Bearer authorization (auth-scheme): bearerAuth
configuration = openapi_client.Configuration(
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.DefaultApi(api_client)
    restart_instance_request = openapi_client.RestartInstanceRequest() # RestartInstanceRequest | 

    try:
        # Restart instances
        api_response = api_instance.restart_instance(restart_instance_request)
        print("The response of DefaultApi->restart_instance:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling DefaultApi->restart_instance: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **restart_instance_request** | [**RestartInstanceRequest**](RestartInstanceRequest.md)|  | 

### Return type

[**RestartInstance200Response**](RestartInstance200Response.md)

### Authorization

[basicAuth](../README.md#basicAuth), [bearerAuth](../README.md#bearerAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**401** | Unauthorized. |  -  |
**403** | Forbidden. |  -  |
**400** | Request parameters were invalid. |  -  |
**404** | Object does not exist. |  -  |
**500** | Something unexpected occurred. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **terminate_instance**
> TerminateInstance200Response terminate_instance(terminate_instance_request)

Terminate an instance

Terminates a given instance.

### Example

* Basic Authentication (basicAuth):
* Bearer (auth-scheme) Authentication (bearerAuth):

```python
import openapi_client
from openapi_client.models.terminate_instance200_response import TerminateInstance200Response
from openapi_client.models.terminate_instance_request import TerminateInstanceRequest
from openapi_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to https://cloud.lambdalabs.com/api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = openapi_client.Configuration(
    host = "https://cloud.lambdalabs.com/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure HTTP basic authorization: basicAuth
configuration = openapi_client.Configuration(
    username = os.environ["USERNAME"],
    password = os.environ["PASSWORD"]
)

# Configure Bearer authorization (auth-scheme): bearerAuth
configuration = openapi_client.Configuration(
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with openapi_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = openapi_client.DefaultApi(api_client)
    terminate_instance_request = openapi_client.TerminateInstanceRequest() # TerminateInstanceRequest | 

    try:
        # Terminate an instance
        api_response = api_instance.terminate_instance(terminate_instance_request)
        print("The response of DefaultApi->terminate_instance:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling DefaultApi->terminate_instance: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **terminate_instance_request** | [**TerminateInstanceRequest**](TerminateInstanceRequest.md)|  | 

### Return type

[**TerminateInstance200Response**](TerminateInstance200Response.md)

### Authorization

[basicAuth](../README.md#basicAuth), [bearerAuth](../README.md#bearerAuth)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**401** | Unauthorized. |  -  |
**403** | Forbidden. |  -  |
**400** | Request parameters were invalid. |  -  |
**404** | Object does not exist. |  -  |
**500** | Something unexpected occurred. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

