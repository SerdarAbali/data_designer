export type CatalogField = {
  id: string;
  object_id: string;
  name: string;
  label: string;
  data_type: string;
  required: boolean;
  nullable: boolean;
  default_value: unknown;
  position: number;
};

export type CatalogObject = {
  id: string;
  system_id: string;
  name: string;
  label: string;
};

export type System = {
  id: string;
  name: string;
  kind: string;
};
