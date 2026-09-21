# The ModelAdmin contract

A `ModelAdmin` is the boundary between the framework and your application.
It declares how a resource should appear in the admin and supplies the
operations needed to read and mutate it.

The shared capabilities are:

- displayed fields and form fields
- search fields, filters, ordering, and pagination
- create, update, and delete operations
- relation fields and inline records
- record and bulk actions
- per-resource permissions and template overrides

The API is intentionally idiomatic in each language. Python uses declarative
class attributes and snake_case hooks; Go uses struct embedding, interfaces,
and functional options. The adapter-specific guides contain complete examples:

- [Python ModelAdmin](../model-admin.md)
- [Go ModelAdmin](../go/reference/model-admin.md)