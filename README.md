# invites-loop-bi

A high-performance, config-driven ELT (Extract, Load, Transform) data pipeline designed to extract operational data from distributed microservices (`iccoli`, `invites_loop`, `ichms`, etc.) and consolidate it into a central OLAP Data Warehouse.

---

## 📌 Overview

`invites-loop-bi` bridges the gap between transactional microservices and analytical reporting. By decoupling read-intensive analytical queries from production transactional DBs and API chains, this pipeline:
- **Eliminates API Chaining Latency**: Provides a centralized Read Model for complex cross-domain analytics.
- **Ensures Data Consistency**: Serves as the Single Source of Truth (SSOT) across all service domains.
- **Optimizes Performance**: Utilizes Polars memory streaming to handle high-throughput extractions efficiently.

---

## ✨ Key Features

- **Config-Driven Ingestion**: Decouples execution engine logic from source definitions. Adding a new table or source requires zero new Python code—only configuration additions.
- **Smart Watermark Tracking**: Supports incremental extraction with automatic fallback strategy (e.g., fallback to `create_datetime` if `update_datetime` is missing or null).
- **High-Performance Extract**: Built on top of **Polars** and **PyArrow / ADBC**, enabling low-memory cursor-based streaming batch extractions.
- **Flexible Load Strategies**: Supports both `FULL_REFRESH` (Truncate & Insert) and `INCREMENTAL` (Merge / Upsert) loading patterns with guaranteed idempotency.
- **Airflow 2.x Ready**: Modular design easily wraps into Airflow DAGs with Dynamic Task Mapping and concurrency control.

---

## 📁 Project Structure

```text
invites-loop-bi/
├── src/
│   ├── config/                     # Source & table extraction configurations
│   │   ├── __init__.py
│   │   ├── iccoli.py               # Extraction configs for iccoli DB
│   │   └── invites_loop.py         # Extraction configs for invites_loop DBs
│   │
│   ├── extract/                    # Universal extraction engine
│   │   ├── __init__.py
│   │   ├── extractor.py            # Polars-based streaming batch extractor
│   │   └── watermark.py            # Watermark manager & state store
│   │
│   ├── load/                       # DW loader modules
│   │   ├── __init__.py
│   │   └── loader.py               # Idempotent target DW loader (Upsert/Truncate)
│   │
│   └── pipeline.py                 # Pipeline execution entry point
│
├── tests/                          # Unit and integration tests
├── .env.example                    # Environment variable template
├── pyproject.toml                  # Project metadata & dependency definitions
└── README.md
```

🛠️ Tech Stack & Prerequisites
Python: 3.10+

Data Processing: Polars, PyArrow, ConnectorX / ADBC

Target Storage: PostgreSQL / Azure PostgreSQL (OLAP DW)

Orchestration: Apache Airflow 2.3+ (Optional for DAG scheduling)
