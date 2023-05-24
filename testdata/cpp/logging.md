---
uid: logging
---

# Logging Components


### Introduction

The client libraries never use logging to report errors, but logging can be enabled to help troubleshoot problems when the last error message does not provide a good enough indication of the root cause.

In general, we abide by the following principles:


- Logging should be controlled by the application developer. Unless explicitly instructed, the libraries produce no output to the console, except to emit a message to `std::clog` immediately before a `GCP_LOG(FATAL)` terminates the process.
- Logging should have very low cost:
  - It should be possible to disable logs at compile time. They should disappear as-if there were `#ifdef`/`#endif` directives around them.
  - A log line at a disabled log level should be about as expensive as an extra `if()` statement. At the very least it should not incur additional memory allocations or locks.
- It should be easy to log complex objects.
- The logging framework should play well with the C++ iostream classes.
- The application should be able to intercept log records and re-direct them to their own logging framework.

### Enabling logs

The application needs to do two things to enable logging:


- First, to configure the destination of the logs you must add a backend (see [AddBackend](xref:classgoogle_1_1cloud_1_1LogSink_1a63ec26a7560bdae9657f250bb93f6a14)) to the default [LogSink](xref:classgoogle_1_1cloud_1_1LogSink_1a06247b1adf1203876402ba6a9be76a7e).
- Second, you must configure what gets logged. Typically, you initialize the `*Connection` object with a [TracingComponentsOption](xref:structgoogle_1_1cloud_1_1TracingComponentsOption). Consult the documentation for each `*Client` class to find what tracing components are available.

At run-time, setting the `GOOGLE_CLOUD_CPP_ENABLE_CLOG` to a non-empty value configures a [LogBackend](xref:classgoogle_1_1cloud_1_1LogBackend) that uses `std::clog`. Likewise, setting the `GOOGLE_CLOUD_CPP_ENABLE_TRACING=a,b` will enable tracing for components `a` and `b` across **all** client objects. The most common components are `auth`, `rpc`, and `rpc-streams`.

Note that while `std::clog` is buffered, the framework will flush any log message at severity `WARNING` or higher.

### Example: Logging From Library

Use the `GCP_LOG()` macro to log from a Google Cloud Platform C++ library:



```cpp
void LibraryCode(ComplexThing const& thing) {
  GCP_LOG(INFO) << "I am here";
  if (thing.is_bad()) {
    GCP_LOG(ERROR) << "Poor thing is bad: " << thing;
  }
}
```

### Example: Enable Logs to std::clog

To enable logs to `std::clog` the application can call:



```cpp
void AppCode() {
  google::cloud::LogSink::EnableStdClog();
}
```

As previously noted, this can be switched at run-time using the `GOOGLE_CLOUD_CPP_ENABLE_CLOG` environment variable. 
