"""Qué depende de un productor y cómo se elimina con él: sus fincas y sus cuentas.

Es el registro de `apps.common.dependents` para productores; la app de productores lo lee al
eliminar uno.
"""

from .dependents import Dependent, DependentRegistry

registry = DependentRegistry()

ProducerDependent = Dependent
register_dependent = registry.register
registered_dependents = registry.all
