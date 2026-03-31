
  # Progressive Flood Mode – Implementation Overview

  The **Progressive Flood Mode** was added to support research planners who need to simulate the gradual accumulation of rainfall over time, rather than the instantaneous overflow used for disaster response. 

  ## Rationale
  - **Disaster Response**: Requires immediate assessment of worst-case flooding. The original “Instant” mode injects a large water head directly at drain and lake nodes.
  - **Research Planning**: Demands realistic progression where rainfall builds up step-by-step, water flows downhill, and flooding emerges naturally.

  By offering both modes, the platform serves two distinct user groups without duplicating the core physics.

  ## Changes Implemented

  ### 1. New Mode Parameter
  A `mode` flag was added to the simulation generator, defaulting to `"progressive"` for research use, but can be set to `"instant"` for disaster response.

  ### 2. Per-Step Rainfall Accumulation
  In progressive mode, the simulation starts with **zero water depth** everywhere.
  - The total rainfall amount (e.g., 150mm) is divided evenly across the simulation steps.
  - Each step receives a fixed, uniform depth of water added to **every node** in the network.
  - This water then flows according to hydraulic head, slope, and surface roughness.

  ### 3. Retention of Hydraulic Physics
  All existing propagation logic—**hydraulic head, slope-weighted flow, and Manning’s roughness**—remains unchanged. Water movement is physically consistent across both modes; only the initial source and timing of water entry differ.

  ### 4. API & Endpoint Support
  - The `/simulate-stream` API now accepts a `mode` query parameter.
  - The compare mode (`/simulate-compare`) also utilizes this parameter, ensuring GA, ACO, and PSO algorithms operate under the same progression model.

  ## Behavioural Differences

  | Aspect | Progressive Mode | Instant Mode |
  | :--- | :--- | :--- |
  | **Rainfall Input** | Added uniformly at every step | Applied once as large head at drains/lakes |
  | **Initial Water** | Zero depth everywhere | High depth at specific drain/lake nodes |
  | **Flood Emergence** | Gradual, from low-lying areas outward | Immediate flooding around drains/lakes |
  | **Primary Use Case** | Research, historical time-series, planning | Disaster response, “what-if” scenarios |

  ## Key Benefits
  - **Realistic Accumulation**: Observe flood evolution in real-time.
  - **Flexibility**: Supports historical rainfall time-series by adjusting per-step amounts.
  - **Consistency**: The same physics engine ensures reliable comparisons between algorithms.

  ## Summary
  The progressive flood mode transforms the simulator from a static, worst-case injector to a **dynamic, incremental rainfall model**. It allows research planners to study flood progression realistically while preserving the high-speed "Instant" mode for operational disaster assessments. All changes are confined to the initialization and water-entry logic; the core flood propagation remains physically accurate across both modes.

