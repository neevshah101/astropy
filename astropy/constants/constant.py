# Licensed under a 3-clause BSD style license - see LICENSE.rst

import functools
import types
import warnings
import numpy as np

from ..units.core import Unit, UnitsError
from ..units.quantity import Quantity
from ..utils import lazyproperty
from ..utils.exceptions import AstropyUserWarning
from ..utils.misc import InheritDocstrings

__all__ = ['Constant', 'EMConstant']


class ConstantMeta(InheritDocstrings):
    """Metaclass for the :class:`Constant`. The primary purpose of this is to
    wrap the double-underscore methods of :class:`Quantity` which is the
    superclass of :class:`Constant`.

    In particular this wraps the operator overloads such as `__add__` to
    prevent their use with constants such as ``e`` from being used in
    expressions without specifying a system.  The wrapper checks to see if the
    constant is listed (by name) in ``Constant._has_incompatible_units``, a set
    of those constants that are defined in different systems of units are
    physically incompatible.  It also performs this check on each `Constant` if
    it hasn't already been performed (the check is deferred until the
    `Constant` is actually used in an expression to speed up import times,
    among other reasons).
    """

    def __new__(mcls, name, bases, d):
        def wrap(meth):
            @functools.wraps(meth)
            def wrapper(self, *args, **kwargs):
                name_lower = self.name.lower()
                instances = self._registry[name_lower]
                if not self._checked_units:
                    for inst in instances.values():
                        try:
                            self.unit.to(inst.unit)
                        except UnitsError:
                            self._has_incompatible_units.add(name_lower)
                    self._checked_units = True

                if (not self.system and
                        name_lower in self._has_incompatible_units):
                    systems = sorted([x for x in instances if x])
                    raise TypeError(
                        'Constant {0!r} does not have physically compatible '
                        'units across all systems of units and cannot be '
                        'combined with other values without specifying a '
                        'system (eg. {1}.{2})'.format(self.abbrev, self.abbrev,
                                                      systems[0]))

                return meth(self, *args, **kwargs)

            return wrapper

        # The wrapper applies to so many of the __ methods that it's easier to
        # just exclude the ones it doesn't apply to
        exclude = set(['__new__', '__array_finalize__', '__array_wrap__',
                       '__dir__', '__getattr__', '__init__', '__str__',
                       '__repr__', '__hash__', '__iter__', '__getitem__',
                       '__len__', '__bool__', '__quantity_subclass__'])
        for attr, value in vars(Quantity).items():
            if (isinstance(value, types.FunctionType) and
                    attr.startswith('__') and attr.endswith('__') and
                    attr not in exclude):
                d[attr] = wrap(value)

        return super().__new__(mcls, name, bases, d)


class Constant(Quantity, metaclass=ConstantMeta):
    """A physical or astronomical constant.

    These objects are quantities that are meant to represent physical
    constants.
    """
    _registry = {}
    _has_incompatible_units = set()

    def __new__(cls, abbrev, name, value, unit, uncertainty,
                reference=None, system=None):
        if reference is None:
            reference = getattr(cls, 'default_reference', None)
            if reference is None:
                raise TypeError("{} requires a reference.".format(cls))
        name_lower = name.lower()
        instances = cls._registry.setdefault(name_lower, {})
        # By-pass Quantity initialization, since units may not yet be
        # initialized here, and we store the unit in string form.
        inst = np.array(value).view(cls)

        if system in instances:
                warnings.warn('Constant {0!r} already has a definition in the '
                              '{1!r} system from {2!r} reference'.format(
                              name, system, reference), AstropyUserWarning)
        for c in instances.values():
            if system is not None and not hasattr(c.__class__, system):
                setattr(c, system, inst)
            if c.system is not None and not hasattr(inst.__class__, c.system):
                setattr(inst, c.system, c)

        instances[system] = inst

        inst._abbrev = abbrev
        inst._name = name
        inst._value = value
        inst._unit_string = unit
        inst._uncertainty = uncertainty
        inst._reference = reference
        inst._system = system

        inst._checked_units = False
        return inst

    def __repr__(self):
        return ('<{0} name={1!r} value={2} uncertainty={3} unit={4!r} '
                'reference={5!r}>'.format(self.__class__, self.name, self.value,
                                          self.uncertainty, str(self.unit),
                                          self.reference))

    def __str__(self):
        return ('  Name   = {0}\n'
                '  Value  = {1}\n'
                '  Uncertainty  = {2}\n'
                '  Unit  = {3}\n'
                '  Reference = {4}'.format(self.name, self.value,
                                           self.uncertainty, self.unit,
                                           self.reference))

    def __quantity_subclass__(self, unit):
        return super().__quantity_subclass__(unit)[0], False

    def copy(self):
        """
        Return a copy of this `Constant` instance.  Since they are by
        definition immutable, this merely returns another reference to
        ``self``.
        """
        return self
    __deepcopy__ = __copy__ = copy

    @property
    def abbrev(self):
        """A typical ASCII text abbreviation of the constant, also generally
        the same as the Python variable used for this constant.
        """

        return self._abbrev

    @property
    def name(self):
        """The full name of the constant."""

        return self._name

    @lazyproperty
    def _unit(self):
        """The unit(s) in which this constant is defined."""

        return Unit(self._unit_string)

    @property
    def uncertainty(self):
        """The known uncertainty in this constant's value."""

        return self._uncertainty

    @property
    def reference(self):
        """The source used for the value of this constant."""

        return self._reference

    @property
    def system(self):
        """The system of units in which this constant is defined (typically
        `None` so long as the constant's units can be directly converted
        between systems).
        """

        return self._system

    def _instance_or_super(self, key):
        instances = self._registry[self.name.lower()]
        inst = instances.get(key)
        if inst is not None:
            return inst
        else:
            return getattr(super(), key)

    @property
    def si(self):
        """If the Constant is defined in the SI system return that instance of
        the constant, else convert to a Quantity in the appropriate SI units.
        """

        return self._instance_or_super('si')

    @property
    def cgs(self):
        """If the Constant is defined in the CGS system return that instance of
        the constant, else convert to a Quantity in the appropriate CGS units.
        """

        return self._instance_or_super('cgs')

    def __array_finalize__(self, obj):
        for attr in ('_abbrev', '_name', '_value', '_unit_string',
                     '_uncertainty', '_reference', '_system'):
            setattr(self, attr, getattr(obj, attr, None))

        self._checked_units = getattr(obj, '_checked_units', False)


class EMConstant(Constant):
    """An electromagnetic constant."""

    @property
    def cgs(self):
        """Overridden for EMConstant to raise a `TypeError`
        emphasizing that there are multiple EM extensions to CGS.
        """

        raise TypeError("Cannot convert EM constants to cgs because there "
                        "are different systems for E.M constants within the "
                        "c.g.s system (ESU, Gaussian, etc.). Instead, "
                        "directly use the constant with the appropriate "
                        "suffix (e.g. e.esu, e.gauss, etc.).")
