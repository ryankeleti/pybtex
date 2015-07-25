# Copyright (c) 2007, 2008, 2009, 2010, 2011, 2012  Andrey Golovizin
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from pybtex.bibtex.exceptions import BibTeXError
from pybtex.bibtex.builtins import builtins, print_warning
from pybtex.bibtex.utils import wrap
from .codegen import PythonCode
#from pybtex.database.input import bibtex


class Variable(object):

    def _undefined(self):
        raise NotImplementedError

    default = property(_undefined)
    value_type = property(_undefined)

    def __init__(self, name, value=None):
        self.set(value)
        self.name = name.lower()

    def __repr__(self):
        return '{0}({1})'.format(type(self).__name__, repr(self._value))
    def set(self, value):
        if value is None:
            value = self.default
        self.validate(value)
        self._value = value
    def validate(self, value):
        if not (isinstance(value, self.value_type) or value is None):
            raise ValueError('Invalid value for BibTeX %s: %s' % (self.__class__.__name__, value))
    def execute(self, interpreter):
        interpreter.push(self.value())

    def write_code(self, interpreter, code):
        code.push('vars[{!r}]._value'.format(self.name))

    def value(self):
        return self._value

    def __repr__(self):
        return u'{0}({1})'.format(type(self).__name__, repr(self.value()))

    def __eq__(self, other):
        return type(self) == type(other) and self._value == other._value


class EntryVariable(Variable):
    def __init__(self, name, interpreter):
        super(EntryVariable, self).__init__(name)
        self.interpreter = interpreter

    def set(self, value):
        if value is not None:
            self.validate(value)
            self.interpreter.current_entry.vars[self.name] = value

    def value(self):
        try:
            return self.interpreter.current_entry.vars[self.name]
        except KeyError:
            return None

    def write_code(self, interpreter, code):
        if self.name not in interpreter.vars:
            raise BibTeXError('undefined entry variable {}'.format(self.name))
        code.push('i.current_entry.vars[{!r}]'.format(self.name))


class Integer(Variable):
    value_type = int
    default = 0


class EntryInteger(Integer, EntryVariable):
    pass


class String(Variable):
    value_type = basestring
    default = ''


class EntryString(String, EntryVariable):
    pass


class Literal(Variable):
    def __init__(self, value):
        self._value = value

    def write_code(self, interpreter, code):
        code.push('{!r}'.format(self.value()))


class IntegerLiteral(Literal):
    pass


class StringLiteral(Literal):
    pass


class MissingField(unicode):
    pass


MISSING_FIELD = MissingField()


class Field(object):
    def __init__(self, name, interpreter):
        self.interpreter = interpreter
        self.name = name.lower()

    def execute(self, interpreter):
        self.interpreter.push(self.value())

    def value(self):
        try:
            return self.interpreter.current_entry.fields[self.name]
        except KeyError:
            return MISSING_FIELD

    def write_code(self, interpreter, code):
        if self.name not in interpreter.vars:
            raise BibTeXError('undefined field {}'.format(self.name))
        code.push('i.current_entry.fields.get({0!r}, MISSING_FIELD)'.format(self.name))


class Crossref(Field):
    def __init__(self, interpreter):
        super(Crossref, self).__init__('crossref', interpreter)

    def value(self):
        try:
            value = self.interpreter.current_entry.fields[self.name]
            crossref_entry = self.interpreter.bib_data.entries[value]
        except KeyError:
            return MISSING_FIELD
        return crossref_entry.key

    def write_code(self, interpreter, code):
        code.push('vars[{!r}].value()'.format(self.name))


class Identifier(object):
    def __init__(self, name):
        self.name = name.lower()

    def __repr__(self):
        return '{0}({1!r})'.format(type(self).__name__, self.name)

    def __eq__(self, other):
        return type(self) == type(other) and self.name == other.name

    def get_var(self, interpreter):
        try:
            var = interpreter.vars[self.name]
        except KeyError:
            raise BibTeXError('can not execute undefined function %s' % self.name)
        return var

    def execute(self, interpreter):
        self.get_var(interpreter).execute(interpreter)

    def write_code(self, interpreter, code):
        self.get_var(interpreter).write_code(interpreter, code)


class QuotedVar(Identifier):
    def write_code(self, interpreter, code):
        try:
            var = interpreter.vars[self.name]
        except KeyError:
            raise BibTeXError('can not push undefined variable %s' % self.name)
        code.push('vars[{!r}]'.format(self.name))


class CodeBlock(object):
    def __init__(self, body):
        self.body = body

    def write_code(self, interpreter, code):
        code.line('def _tmp_():')
        with code.nested() as body:
            for element in self.body:
                element.write_code(interpreter, body)


class FunctionLiteral(object):
    def __init__(self, body=None):
        if body is None:
            body = []
        self.body = body

    def __repr__(self):
        return u'{0}({1})'.format(type(self).__name__, repr(self.body))

    def __eq__(self, other):
        return type(self) == type(other) and self.body == other.body

    def execute(self, interpreter):
        self.f()
#        print 'executing function', self.body
        #for element in self.body:
            #element.execute(interpreter)

    def write_code(self, interpreter, code):
        function = CodeBlock(self.body)
        function.write_code(interpreter, code)
        code.push('Function("", _tmp_)')


class Function(FunctionLiteral):
    def __init__(self, name, f):
        self.name = name.lower()
        self.f = f
        super(Function, self).__init__()

    def __repr__(self):
        return u'{0}({1}){2!r}'.format(type(self).__name__, self.name, self.body)

    def write_code(self, interpreter, code):
        code.line('vars[{!r}].f()'.format(self.name))


class Builtin(object):
    def __init__(self, name):
        self.name = name
        self.f = builtins[name]

    def execute(self, interpreter):
        self.f(interpreter)

    def __repr__(self):
        return '<builtin %s>' % self.name

    def write_code(self, interpreter, code):
        code.line('builtins[{!r}](i)'.format(self.name))


class Interpreter(object):
    def __init__(self, bib_format, bib_encoding):
        self.bib_format = bib_format
        self.bib_encoding = bib_encoding
        self.stack = []
        self.push = self.stack.append
        self.pop = self.stack.pop
        self.vars = {}
        for name in builtins:
            self.add_variable(Builtin(name))
        self.add_variable(Integer('global.max$', 20000))  # constants taken from
        self.add_variable(Integer('entry.max$', 250))     # BibTeX 0.99d (TeX Live 2012)
        self.add_variable(EntryString('sort.key$', self))
        self.macros = {}
        self.output_buffer = []
        self.output_lines = []

    def get_token(self):
        return self.bst_script.next()

    def add_variable(self, var):
        if var.name in self.vars:
            raise BibTeXError('variable "{0}" already declared as {1}'.format(name, type(value).__name__))
        self.vars[var.name] = var

    def output(self, string):
        self.output_buffer.append(string)

    def newline(self):
        output = wrap(u''.join(self.output_buffer))
        self.output_lines.append(output)
        self.output_lines.append(u'\n')
        self.output_buffer = []

    def exec_code(self, code):
        bytecode = code.compile()
        context = {
            'i': self,
            'push': self.push,
            'vars': self.vars,
            'builtins': builtins,
            'Function': Function,
            'MISSING_FIELD': MISSING_FIELD,
        }
        exec bytecode in context
        return context

    def run(self, bst_script, citations, bib_files, min_crossrefs):
        """Run bst script and return formatted bibliography."""

        self.bst_script = iter(bst_script)
        self.citations = citations
        self.bib_files = bib_files
        self.min_crossrefs = min_crossrefs

        for command in self.bst_script:
            name = command[0]
            args = command[1:]
            method = 'command_' + name.lower()
            if hasattr(self, method):
                getattr(self, method)(*args)
            else:
                print 'Unknown command', name

        return u''.join(self.output_lines)

    def command_entry(self, fields, ints, strings):
        for id in fields:
            name = id.name
            self.add_variable(Field(name, self))
        self.add_variable(Crossref(self))
        for id in ints:
            name = id.name
            self.add_variable(EntryInteger(name, self))
        for id in strings:
            name = id.name
            self.add_variable(EntryString(name, self))

    def command_execute(self, command_):
#        print 'EXECUTE'
        command_[0].execute(self)

    def command_function(self, name_, body):
        name = name_[0].name
        block = CodeBlock(body)
        code = PythonCode()
        block.write_code(self, code)
        #from pprint import pprint
        #pprint(body, indent=4)
        #print
        #print code.stream.getvalue()
        context = self.exec_code(code)
        func = Function(name, context['_tmp_'])
        self.add_variable(func)

    def command_integers(self, identifiers):
#        print 'INTEGERS'
        for identifier in identifiers:
            self.add_variable(Integer(identifier.name))

    def command_iterate(self, function_group):
        function = function_group[0].name
        self._iterate(function, self.citations)

    def _iterate(self, function, citations):
        f = self.vars[function]
        for key in citations:
            self.current_entry_key = key
            self.current_entry = self.bib_data.entries[key]
            f.execute(self)
        self.currentEntry = None

    def command_macro(self, name_, value_):
        name = name_[0].name
        value = value_[0].value()
        self.macros[name] = value

    def command_read(self):
#        print 'READ'
        p = self.bib_format(
            encoding=self.bib_encoding,
            macros=self.macros,
            person_fields=[],
            wanted_entries=self.citations,
        )
        self.bib_data = p.parse_files(self.bib_files)
        self.citations = self.bib_data.add_extra_citations(self.citations, self.min_crossrefs)
        self.citations = list(self.remove_missing_citations(self.citations))
#        for k, v in self.bib_data.iteritems():
#            print k
#            for field, value in v.fields.iteritems():
#                print '\t', field, value
#        pass

    def remove_missing_citations(self, citations):
        for citation in citations:
            if citation in self.bib_data.entries:
                yield citation
            else:
                print_warning('missing database entry for "{0}"'.format(citation))

    def command_reverse(self, function_group):
        function = function_group[0].name
        self._iterate(function, reversed(self.citations))

    def command_sort(self):
        def key(citation):
            return self.bib_data.entries[citation].vars['sort.key$']
        self.citations.sort(key=key)

    def command_strings(self, identifiers):
        #print 'STRINGS'
        for identifier in identifiers:
            self.add_variable(String(identifier.name))

    @staticmethod
    def is_missing_field(field):
        return field is MISSING_FIELD
