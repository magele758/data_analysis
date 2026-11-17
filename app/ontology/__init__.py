from app.ontology.object_type import ObjectType, PropertyMeta
from app.ontology.interface_type import InterfaceType
from app.ontology.link_type import LinkType
from app.ontology.action_type import (
    ActionType,
    ActionParameter,
    ActionPrecondition,
    ActionExecutionAudit,
    FunctionType,
)
from app.ontology.ontology_engine import (
    OntologyEngine,
    build_object_type_from_asset,
    get_ontology_engine,
)
