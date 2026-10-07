# Protocol interfaces and explicit adapters

Domain services depend on feature-specific protocols, with memory and production adapters implementing the same interface. Explicit constructor injection makes replacement and testing straightforward without introducing a framework-owned container or plugin discovery system.
