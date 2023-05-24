---
uid: indexpage
---

# Common Components for the Google Cloud C++ Client Libraries


## Overview

This library contains common components shared by all the Google Cloud C++ Client Libraries. Including:


- [Credentials](xref:classgoogle_1_1cloud_1_1Credentials) are used to configure authentication in the client libraries. See [Authentication Components](xref:group__guac) for more details on authentication.
- [Options](xref:classgoogle_1_1cloud_1_1Options) are used to override the client library default configuration. See [Client Library Configuration](xref:group__options) for more details on library configuration.
- [Status](xref:classgoogle_1_1cloud_1_1Status) error codes and details from an operation.
- [StatusOr<T>](xref:classgoogle_1_1cloud_1_1StatusOr) returns a value on success and a `Status` on error.
- [future<T>](xref:classgoogle_1_1cloud_1_1future) and [promise<T>](xref:classgoogle_1_1cloud_1_1promise) futures (a holder that will receive a value asynchronously) and promises (the counterpart of a future, where values are stored asynchronously). They satisfy the API for `std::future` and `std::promise`, and add support for callbacks and cancellation.



<aside class="warning"><b>Warning:</b>

Some namespaces are reserved for implementation details and are subject to change without notice. Do not use any symbols in these namespaces as your application may break when trying to use future versions of the library.
These namespaces include:

- Any namespace with `internal` in its name, including `google::cloud::internal` and `google::cloud::rest_internal`.
- Any namespace with `testing` in its name, including `google::cloud::testing_util`. 
</aside>

### More information


- [Error Handling](xref:common-error-handling) for more details about how the libraries report run-time errors and how you can handle them.
- [Client Library Configuration](xref:group__options) for information about configuring the client libraries at runtime.
- [Authentication Components](xref:group__guac) for more details about how to configure authentication in the client libraries.
- [Logging Components](xref:logging) for information about enabling logging to the console in the client libraries. 
