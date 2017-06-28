import jinja2
import os
from datetime import datetime

from . import trait_extractors as tx
from . import utils


OBJECT_TEMPLATE = '''# {{ cls.filename }}
# Auto-generated by altair_parser {{ date }}

{%- for import in cls.basic_imports %}
{{ import }}
{%- endfor %}

{#-
def Instance(classname, *args, **kwargs):
    """Convenience routine for an instance of a class in this file"""
    return jst.JSONInstance(__name__ + '.' + classname, *args, **kwargs)
-#}

{% for cls in classes %}
{{ cls.object_code() }}
{% endfor %}
'''


class JSONSchema(object):
    """A class to wrap JSON Schema objects and reason about their contents"""
    object_template = OBJECT_TEMPLATE
    __draft__ = 4

    attr_defaults = {'title': '',
                     'description': '',
                     'properties': {},
                     'definitions': {},
                     'default': None,
                     'examples': {},
                     'type': 'object',
                     'required': [],
                     'additionalProperties': True}
    basic_imports = ["import traitlets as T",
                     "from . import jstraitlets as jst"]

    # an ordered list of trait extractor classes.
    # these will be checked in-order, and return a trait_code when
    # a match is found.
    trait_extractors = [tx.AnyOfObject, tx.OneOfObject, tx.AllOfObject,
                        tx.RefObject, tx.RefTrait,
                        tx.Not, tx.AnyOf, tx.AllOf, tx.OneOf,
                        tx.Enum, tx.SimpleType, tx.CompoundType,
                        tx.Array, tx.Object, ]

    def __init__(self, schema, module=None, context=None,
                 parent=None, name=None, metadata=None,
                 definition_tags=('definitions',)):
        if not isinstance(schema, dict):
            raise ValueError("schema should be supplied as a dict")

        self.schema = schema
        self.module = module
        self.parent = parent
        self.name = name
        self.metadata = metadata or {}

        # if context is not given, then assume this is a root instance that
        # defines its own context
        self.context = context or self
        self.definition_tags = definition_tags
        self._trait_extractor = None

    @classmethod
    def from_json_file(cls, filename, **kwargs):
        """Instantiate a JSONSchema object from a JSON file"""
        import json
        with open(filename) as f:
            schema = json.load(f)
        return cls(schema, **kwargs)

    @property
    def all_definitions(self):
        defs = {}
        for tag in self.definition_tags:
            defs.update(self.schema.get(tag, {}))
        return defs

    @property
    def trait_extractor(self):
        if self._trait_extractor is None:
            # TODO: handle multiple matches with an AllOf()
            for TraitExtractor in self.trait_extractors:
                trait_extractor = TraitExtractor(self)
                if trait_extractor.check():
                    self._trait_extractor = trait_extractor
                    break
            else:
                raise ValueError("No recognized trait code for schema with "
                                 "keys {0}".format(tuple(self.schema.keys())))
        return self._trait_extractor

    def indented_description(self, indent_level=2):
        return utils.format_description(self.description,
                                        indent=4 * indent_level)

    def copy(self, **kwargs):
        """Make a copy, optionally overwriting any init arguments"""
        kwds = dict(schema=self.schema, module=self.module,
                    context=self.context, parent=self.parent,
                    name=self.name, metadata=self.metadata)
        kwds.update(kwargs)
        return self.__class__(**kwds)

    def make_child(self, schema, name=None, metadata=None):
        """
        Make a child instance, appropriately defining the parent and context
        """
        return self.__class__(schema, module=self.module, context=self.context,
                              parent=self, name=name, metadata=metadata)

    def __getitem__(self, key):
        return self.schema[key]

    def __contains__(self, key):
        return key in self.schema

    def __getattr__(self, attr):
        if attr in self.attr_defaults:
            return self.schema.get(attr, self.attr_defaults[attr])
        raise AttributeError(f"'{self.__class__.__name__}' object "
                             f"has no attribute '{attr}'")

    def get(self, *args):
        return self.schema.get(*args)

    @property
    def is_root(self):
        return self.context is self

    @property
    def is_trait(self):
        if 'anyOf' in self or 'allOf' in self or 'oneOf' in self:
            return True
        else:
            return self.type != 'object' and not self.is_reference

    def really_is_trait(self):
        if self.type != 'object':
            return True
        elif 'properties' in self:
            return False
        elif '$ref' in self:
            return self.wrapped_ref().really_is_trait()
        elif 'anyOf' in self:
            return all(self.make_child(spec).really_is_trait()
                       for spec in self['anyOf'])
        elif 'allOf' in self:
            return all(self.make_child(spec).really_is_trait()
                       for spec in self['allOf'])
        elif 'oneOf' in self:
            return all(self.make_child(spec).really_is_trait()
                       for spec in self['oneOf'])
        else:
            return False

    def really_is_object(self):
        if 'properties' in self:
            return True
        elif '$ref' in self:
            return self.wrapped_ref().really_is_object()
        elif 'anyOf' in self:
            return all(self.make_child(spec).really_is_object()
                       for spec in self['anyOf'])
        elif 'allOf' in self:
            return all(self.make_child(spec).really_is_object()
                       for spec in self['allOf'])
        elif 'oneOf' in self:
            return all(self.make_child(spec).really_is_object()
                       for spec in self['oneOf'])
        else:
            return False

    @property
    def is_object(self):
        if 'anyOf' in self or 'allOf' in self or 'oneOf' in self:
            return False
        else:
            return self.type == 'object' and not self.is_reference

    @property
    def is_reference(self):
        return '$ref' in self.schema

    @property
    def is_named_object(self):
        try:
            return bool(self.classname)
        except NotImplementedError:
            return False

    @property
    def classname(self):
        if self.name:
            return utils.regularize_name(self.name)
        elif self.is_root:
            return "Root"
        elif self.is_reference:
            return utils.regularize_name(self.schema['$ref'].split('/')[-1])
        else:
            raise NotImplementedError("class name for schema with keys "
                                      "{0}".format(tuple(self.schema.keys())))

    @property
    def full_classname(self):
        if not self.module:
            return self.classname
        else:
            return self.module + '.' + self.classname

    @property
    def schema_hash(self):
        return utils.hash_schema(self.schema)

    @property
    def modulename(self):
        return 'schema'

    @property
    def filename(self):
        return self.modulename + '.py'

    @property
    def baseclass(self):
        return "jst.JSONHasTraits"

    @property
    def additional_traits(self):
        if self.additionalProperties in [True, False]:
            return repr(self.additionalProperties)
        else:
            trait = self.make_child(self.additionalProperties)
            return "[{0}]".format(trait.trait_code)

    @property
    def import_statement(self):
        return self.trait_extractor.import_statement()

    def wrapped_definitions(self):
        """Return definition dictionary wrapped as JSONSchema objects"""
        return {name.lower(): self.make_child(schema, name=name)
                for name, schema in self.all_definitions.items()}

    def wrapped_properties(self):
        """Return property dictionary wrapped as JSONSchema objects"""
        return {utils.regularize_name(name): self.make_child(val, metadata={'required': name in self.required})
                for name, val in self.properties.items()}

    def wrapped_ref(self):
        return self.get_reference(self.schema['$ref'])

    def get_reference(self, ref):
        """
        Get the JSONSchema object for the given reference code.

        Reference codes should look something like "#/definitions/MyDefinition"
        """
        if not ref:
            raise ValueError("empty reference")

        path = ref.split('/')
        name = path[-1]
        if path[0] != '#':
            raise ValueError(f"Unrecognized $ref format: '{ref}'")
        elif len(path) == 1 or path[1] == '':
            return self.context
        try:
            schema = self.context.schema
            for key in path[1:]:
                schema = schema[key]
        except KeyError:
            raise ValueError(f"$ref='{ref}' not present in the schema")

        return self.make_child(schema, name=name)

    @property
    def trait_code(self):
        """Create the trait code for the given schema"""
        if self.metadata.get('required', False):
            kwargs = {'allow_undefined': False}
        else:
            kwargs = {}

        # TODO: handle multiple matches with an AllOf()
        for TraitExtractor in self.trait_extractors:
            trait_extractor = TraitExtractor(self)
            if trait_extractor.check():
                return trait_extractor.trait_code(**kwargs)
        else:
            raise ValueError("No recognized trait code for schema with "
                             "keys {0}".format(tuple(self.schema.keys())))

    def object_code(self):
        """Return code to define an object for this schema"""
        # TODO: handle multiple matches with an AllOf()
        for TraitExtractor in self.trait_extractors:
            trait_extractor = TraitExtractor(self)
            if trait_extractor.check():
                return trait_extractor.object_code()
        else:
            raise ValueError("No recognized object code for schema with "
                             "keys {0}".format(tuple(self.schema.keys())))

    @property
    def trait_imports(self):
        """Return the list of imports required in the trait_code definition"""
        # TODO: handle multiple matches with an AllOf()
        for TraitExtractor in self.trait_extractors:
            trait_extractor = TraitExtractor(self)
            if trait_extractor.check():
                return trait_extractor.trait_imports()
        else:
            raise ValueError("No recognized trait code for schema with "
                             "keys {0}".format(tuple(self.schema.keys())))

    @property
    def object_imports(self):
        """Return the list of imports required in the object_code definition"""
        imports = list(self.basic_imports)
        if isinstance(self.additionalProperties, dict):
            default = self.make_child(self.additionalProperties)
            imports.extend(default.trait_imports)
        if self.is_reference:
            imports.append(self.wrapped_ref().import_statement)
        for trait in self.wrapped_properties().values():
            imports.extend(trait.trait_imports)
        return sorted(set(imports), reverse=True)

    @property
    def module_imports(self):
        """List of imports of all definitions for the root module"""
        imports = [self.import_statement]
        for obj in self.wrapped_definitions().values():
            imports.append(obj.import_statement)
        return [i for i in imports if i]

    def source_tree(self):
        """Return the JSON specification of the module source tree

        This can be passed to ``altair_parser.utils.load_dynamic_module``
        or to ``altair_parser.utils.save_module``
        """
        assert self.is_root

        template = jinja2.Template(self.object_template)

        classes = [self]

        # Determine list of classes to generate
        classes += [schema for schema in self.wrapped_definitions().values()]
        date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        modspec = {
            'jstraitlets.py': open(os.path.join(os.path.dirname(__file__),
                                   'src', 'jstraitlets.py')).read(),
            self.filename: template.render(cls=self, classes=classes, date=date)
        }

        modspec['__init__.py'] = '\n'.join(self.module_imports)

        return modspec
