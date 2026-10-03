"""Qué depende de una finca y cómo se elimina con ella: sus parcelas.

Es el registro de `apps.common.dependents` para fincas; la app de fincas lo lee al eliminar una.
"""

from .dependents import Dependent, DependentRegistry

registry = DependentRegistry()

FarmDependent = Dependent
register_dependent = registry.register
registered_dependents = registry.all
