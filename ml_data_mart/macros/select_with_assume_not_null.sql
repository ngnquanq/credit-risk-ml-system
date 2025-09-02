{% macro select_with_assume_not_null(table, schema=target.schema, database=target.database, cols_to_force=['SK_ID_CURR']) %}
  {%- set relation = adapter.get_relation(database=database, schema=schema, identifier=table) -%}
  {%- set cols = adapter.get_columns_in_relation(relation) -%}
  SELECT
  {%- for col in cols %}
    {%- if col.name in cols_to_force %}
    assumeNotNull({{ col.name }}) AS {{ col.name }}
    {%- else %}
    {{ col.name }}
    {%- endif -%}
    {%- if not loop.last %},{% endif %}
  {%- endfor %}
  FROM {{ relation }}
{% endmacro %}