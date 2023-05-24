---
uid: common-error-handling
---

# Error Handling


### Overview

In general, the `google-cloud-cpp` libraries return a [StatusOr<T>](xref:classgoogle_1_1cloud_1_1StatusOr) if a function may fail and needs to signal an error. `StatusOr<T>` is an "outcome", it contains either the value returned on success, or a description of the error. Errors are represented by [Status](xref:classgoogle_1_1cloud_1_1Status), thus the name. If you are familiar with `std::expected` from C++23, `StatusOr<T>` plays a similar role, but does not attempt to be compatible with it.

If you are planning to log a `Status`, consider using the [iostream operator<<](xref:namespacegoogle_1_1cloud_1adbc883f10549b827f82c93be159ffdd6). A `Status` contains more than just the message, in particular, its [error_info()](xref:classgoogle_1_1cloud_1_1Status_1a172e846ab5623d78d49e2ed128f49583) member function may return additional information that is useful during troubleshooting.

### Stream Ranges

Some functions return [StreamRange<S>](xref:classgoogle_1_1cloud_1_1StreamRange), where `S` is a `StatusOr<T>`. These ranges provide [input iterators](https://en.cppreference.com/w/cpp/named_req/InputIterator) that paginate or stream results from a service, offering a more idiomatic API. The value type in these iterators is `StatusOr<T>` because the stream may fail after it has successfully returned some values. For example, if the request to obtain the next page of results fails, or if the underlying stream is interrupted by the service.

### Futures

Some functions return a "future" ([future<T>](xref:classgoogle_1_1cloud_1_1future)). These objects represent a value that will be obtained asynchronously. By the very nature of asynchronous operations, the request may fail after the function is called. Therefore, we have chosen to return `future<StatusOr<T>>`. We think the alternatives are either incorrect (e.g. `StatusOr<future<T>>` can only handle errors detected before the function returns), or overly complex (`StatusOr<future<StatusOr<T>>>`).

### Values with specific error handling

Some functions return a value that already has a mechanism to signal failures. For example:


- Some functions return [AsyncStreamingReadWriteRpc<T,U>](xref:classgoogle_1_1cloud_1_1AsyncStreamingReadWriteRpc). Or to be technical, they return `std::unique_ptr<AsyncStreamingReadWriteRpc<T,U>>`.
- A small number of functions return classes derived from `std::istream` or `std::ostream`.

In such cases, the library does not wrap the result in a `StatusOr<T>` because the returned type already has mechanisms to signal errors.

### Example: Using StatusOr<T>

You can check that a `StatusOr<T>` contains a value by calling the `.ok()` method, or by using `operator bool()` (like with other smart pointers). If there is no value, you can access the contained `Status` object using the `.status()` member. If there is a value, you may access it by dereferencing with `operator*()` or `operator->()`. As with all smart pointers, callers must first check that the `StatusOr<T>` contains a value before dereferencing and accessing the contained value.



```cpp
  namespace gc = ::google::cloud;
  [](std::string const& project_name) {
    gc::StatusOr<gc::Project> project = gc::MakeProject(project_name);
    if (!project) {
      std::cerr << "Error parsing project <" << project_name
                << ">: " << project.status() << "\n";
      return;
    }
    std::cout << "The project id is " << project->project_id() << "\n";
  }
```

### Example: Using StatusOr<T> with exceptions

Some applications prefer to throw exceptions on errors. In this case, consider using [`StatusOr<T>::value()`](xref:classgoogle_1_1cloud_1_1StatusOr_1aeb1f35f6c7b8b5d56641a6f2bb1c9697). This function throws a [RuntimeStatusError](xref:classgoogle_1_1cloud_1_1RuntimeStatusError) if there is no value, and returns the value otherwise.



<aside class="note"><b>Note:</b>
If you're compiling with exceptions disabled, calling `.value()` on a `StatusOr<T>` that does not contain a value will terminate the program instead of throwing.
</aside>

```cpp
  namespace gc = ::google::cloud;
  [](std::string const& project_name) {
    try {
      gc::Project project = gc::MakeProject(project_name).value();
      std::cout << "The project id is " << project.project_id() << "\n";
    } catch (gc::RuntimeStatusError const& ex) {
      std::cerr << "Error parsing project <" << project_name
                << ">: " << ex.status() << "\n";
    }
  }
```

### Error Handling in google-cloud-cpp code samples

The code samples for `google-cloud-cpp` try to emphasize how to use specific APIs and often have minimal error handling. A typical code sample may simply throw the status on error, like so:



```cpp
namespace svc = ::google::cloud::some_service;
[](svc::Client client, std::string const& key) {
    auto response = client.SomeRpc(key);
    if (!response) throw std::move(response).status();
    // ... example continues here ...
}
```

This should not be interpreted as a best practice. If your application is designed to work with exceptions, then using [`StatusOr<T>::value()`](xref:classgoogle_1_1cloud_1_1StatusOr_1aeb1f35f6c7b8b5d56641a6f2bb1c9697) is a better alternative. We just want to show that some error handling is required for these functions, but at the same time we don't want to obscure the example with a lot of error handling code.



###### See Also

[`google::cloud::StatusOr`](xref:classgoogle_1_1cloud_1_1StatusOr)

###### See Also

[`google::cloud::Status`](xref:classgoogle_1_1cloud_1_1Status) the class used to describe errors. 

###### See Also

[`google::cloud::future`](xref:classgoogle_1_1cloud_1_1future) for more details on the type returned by asynchronous operations. 

###### See Also

[`google::cloud::AsyncStreamingReadWriteRpc`](xref:classgoogle_1_1cloud_1_1AsyncStreamingReadWriteRpc) for more details on error handling for this class template. 

###### See Also

[https://en.cppreference.com/w/cpp/utility/expected](https://en.cppreference.com/w/cpp/utility/expected) for more information about `std::expected`
