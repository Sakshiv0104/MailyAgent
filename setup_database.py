import os
import pandas as pd
import sqlite3
import networkx as nx
import matplotlib.pyplot as plt
import json

# --- Configuration ---
DATA_DIR = "data"
DB_NAME = "database.sqlite"
DIAGRAM_FILE = "schema_diagram.png"
METADATA_FILE = "schema_metadata.json"


def clean_name(name):
    return name.strip().lower().replace(" ", "_")


def create_smart_views(conn, cursor, schema_info, tables):
    """Automatically create pre-joined views based on detected foreign keys"""
    print("\n Creating Smart Pre-Joined Views...")

    view_source    = {}
    view_table_des = {}

    table_connections = {t: len(info["fks"]) for t, info in schema_info.items()}
    sorted_tables = sorted(table_connections.items(), key=lambda x: x[1], reverse=True)

    for fact_table, fk_count in sorted_tables:
        if fk_count == 0:
            continue

        fks = schema_info[fact_table]["fks"]

        for fk in fks:
            ref_table = fk["ref_table"]
            join_col  = fk["col"]
            ref_col   = fk["ref_col"]

            view_name = f"{fact_table}_{ref_table}_master_view"

            fact_cols = [f'fact."{col}" as {fact_table}_{col}' for col in tables[fact_table].columns]
            dim_cols  = [f'dim."{col}" as {ref_table}_{col}'  for col in tables[ref_table].columns]
            all_cols  = fact_cols + dim_cols

            sql = f"""
                CREATE VIEW IF NOT EXISTS {view_name} AS
                SELECT {', '.join(all_cols)}
                FROM {fact_table} fact
                LEFT JOIN {ref_table} dim ON fact."{join_col}" = dim."{ref_col}"
            """

            try:
                cursor.execute(f"DROP VIEW IF EXISTS {view_name}")
                cursor.execute(sql)
                print(f"  Created view: {view_name}")

                # Capture sample row for metadata
                cursor.execute(f"SELECT * FROM {view_name} LIMIT 1")
                row       = cursor.fetchone()
                col_names = [d[0] for d in cursor.description]

                if row:
                    view_table_des[view_name] = {col: str(val) for col, val in zip(col_names, row)}
                else:
                    view_table_des[view_name] = {col: "N/A" for col in col_names}

                view_source[view_name] = [fact_table, ref_table]

            except Exception as e:
                print(f"  Could not create {view_name}: {e}")

    conn.commit()
    return view_source, view_table_des


def analyze_and_ingest():
    print(f"Starting Smart Data Analysis in '{DATA_DIR}'...")

    # 1. Load all CSVs
    tables = {}
    try:
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]
    except FileNotFoundError:
        print(f"Error: Folder '{DATA_DIR}' not found.")
        return

    for file in files:
        table_name = file.replace(".csv", "").lower()
        df = pd.read_csv(os.path.join(DATA_DIR, file))
        df.columns = [clean_name(c) for c in df.columns]
        tables[table_name] = df
        print(f"  Loaded: {table_name} ({len(df)} rows)")

    # 2. Find Primary Keys
    schema_info = {}
    print("\n Identifying Primary Keys...")
    for name, df in tables.items():
        possible_pk = None
        candidates = [c for c in df.columns if c == 'id' or c == f"{name}_id" or c == f"{name}id"]
        if not candidates and len(df.columns) > 0:
            first = df.columns[0]
            if 'id' in first or 'code' in first or 'number' in first:
                candidates.append(first)
        for col in candidates:
            if df[col].is_unique and not df[col].isnull().any():
                possible_pk = col
                break
        schema_info[name] = {"pk": possible_pk, "fks": []}
        print(f"  '{name}': PK = {possible_pk}")

    # 3. Find Foreign Keys with data validation
    print("\n Identifying Relationships...")
    for child_table, child_df in tables.items():
        for col in child_df.columns:
            if col == schema_info[child_table]["pk"]:
                continue
            for parent_table, info in schema_info.items():
                if child_table == parent_table: continue
                parent_pk = info["pk"]
                if not parent_pk: continue

                is_name_match = False
                if col == parent_pk: is_name_match = True
                elif col == f"{parent_table}_id" or col == f"{parent_table}id": is_name_match = True
                elif parent_table.endswith('s') and (col == f"{parent_table[:-1]}_id" or col == f"{parent_table[:-1]}id"): is_name_match = True
                elif parent_pk in col: is_name_match = True

                if is_name_match:
                    child_vals  = set(child_df[col].dropna().unique())
                    parent_vals = set(tables[parent_table][parent_pk].unique())
                    if len(child_vals) == 0: continue
                    overlap = len(child_vals.intersection(parent_vals)) / len(child_vals)
                    if overlap > 0.7:
                        print(f"  FK: {child_table}.{col} → {parent_table}.{parent_pk} ({int(overlap*100)}% overlap)")
                        schema_info[child_table]["fks"].append({
                            "col": col, "ref_table": parent_table, "ref_col": parent_pk
                        })

    # 4. Create Database
    if os.path.exists(DB_NAME): os.remove(DB_NAME)
    conn   = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("\n Creating Database Tables...")
    for name, df in tables.items():
        cols_sql = []
        pk = schema_info[name]["pk"]
        for col in df.columns:
            dtype = "TEXT"
            if pd.api.types.is_integer_dtype(df[col]): dtype = "INTEGER"
            elif pd.api.types.is_float_dtype(df[col]): dtype = "REAL"
            line = f'"{col}" {dtype}'
            if col == pk: line += " PRIMARY KEY"
            cols_sql.append(line)
        for fk in schema_info[name]["fks"]:
            cols_sql.append(f'FOREIGN KEY ("{fk["col"]}") REFERENCES "{fk["ref_table"]}" ("{fk["ref_col"]}")')
        cursor.execute(f"CREATE TABLE {name} ({', '.join(cols_sql)});")
        df.to_sql(name, conn, if_exists='append', index=False)
        print(f"  Table created: {name}")

    # 5. Create Views + capture metadata
    view_source, view_table_des = create_smart_views(conn, cursor, schema_info, tables)

    # 6. Build and save metadata
    metadata = {"base_tables": {}, "view_source": view_source, "view_table_des": view_table_des}
    for name, df in tables.items():
        sample = df.iloc[0].to_dict() if not df.empty else {c: "N/A" for c in df.columns}
        metadata["base_tables"][name] = {k: str(v) for k, v in sample.items()}

    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"\n Metadata saved to {METADATA_FILE}")

    # 7. ER Diagram
    print("\n Generating Diagram...")
    G = nx.DiGraph()
    for table in schema_info: G.add_node(table)
    for child, info in schema_info.items():
        for fk in info["fks"]:
            G.add_edge(child, fk["ref_table"], label=fk["col"])
    pos = nx.spring_layout(G, k=2, iterations=50)
    plt.figure(figsize=(12, 8))
    nx.draw(G, pos, with_labels=True, node_size=3000, node_color='lightblue',
            font_weight='bold', node_shape="s", edge_color='gray')
    nx.draw_networkx_edge_labels(G, pos, edge_labels={(u, v): d["label"] for u, v, d in G.edges(data=True)})
    plt.savefig(DIAGRAM_FILE)

    conn.close()
    print(f"\n Setup complete!")
    print(f"  Base tables : {len(metadata['base_tables'])}")
    print(f"  Views       : {len(view_source)}")


if __name__ == "__main__":
    analyze_and_ingest()