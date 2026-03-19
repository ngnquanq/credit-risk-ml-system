from feast import Entity, ValueType

customer = Entity(
    name="customer",
    join_keys=["sk_id_curr"],
    description="Loan application customer id",
    value_type=ValueType.STRING,
)
