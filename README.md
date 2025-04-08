# toolbox

Containerization and setup tools for bootstrapping my ML research projects.

Install ai commit hook:

```bash
curl -s https://raw.githubusercontent.com/sidnb13/toolbox/refs/heads/master/utils/download.sh | bash
```

Backlog:

- Skypilot integration to spin up instances from cli
- Use a per-project config file for advanced configuration
- integration with ray job queue and gpuboard project for observability
- cleaner, less hardcoded defaults for dockerfiles, etc.
- Rich devcontainer support

```mermaid
graph TB
    classDef controller fill:#2E5EAA,stroke:#173A7B,color:white
    classDef ray fill:#0194E2,stroke:#015B8C,color:white
    classDef container fill:#67B7D1,stroke:#4A8396,color:white
    classDef storage fill:#FFA500,stroke:#CC8400,color:white
    classDef cli fill:#4CAF50,stroke:#357935,color:white

    Storage[(Remote Storage<br>FUSE/S3)]
    Controller[Controller Service<br>Job Monitor & Resource Manager]:::controller
    CLI[Local CLI Tool]:::cli

    subgraph Instance1
        I1_Ray[Ray Cluster]:::ray
        I1_C1[Container 1]:::container
        I1_C2[Container 2]:::container
    end

    subgraph Instance2
        I2_Ray[Ray Cluster]:::ray
        I2_C1[Container 1]:::container
    end

    subgraph InstanceN
        IN_Ray[Ray Cluster]:::ray
        IN_C1[Container 1]:::container
        IN_C2[Container 2]:::container
    end

    CLI -->|Commands & Monitoring| Controller
    Controller -->|Monitor/Control| Instance1
    Controller -->|Monitor/Control| Instance2
    Controller -->|Monitor/Control| InstanceN

    I1_C1 -->|Submit Jobs| I1_Ray
    I1_C2 -->|Submit Jobs| I1_Ray

    I2_C1 -->|Submit Jobs| I2_Ray

    IN_C1 -->|Submit Jobs| IN_Ray
    IN_C2 -->|Submit Jobs| IN_Ray

    Instance1 -.->|Data| Storage
    Instance2 -.->|Data| Storage
    InstanceN -.->|Data| Storage

    Controller -.->|Job Status & Metrics| CLI
```
