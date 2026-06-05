# Source adapter model

The repo separates shared benchmark infrastructure from source-specific setup.

## Shared layer

- Fabric capacity provisioning
- Benchmark VM provisioning
- Networking and firewall baseline
- Fabric REST/fabric-cli setup helpers
- Initial sync polling against the Fabric SQL endpoint
- CDC marker measurement against the Fabric SQL endpoint
- Result summarization

## Source layer

Each source adapter owns:

- Source database infrastructure
- Source prerequisites
- Source-specific HammerDB scripts or instructions
- Source-specific Fabric tutorial link
- Validation status and caveats

## Status vocabulary

- `Implemented and live deployment validated`: deployed at least once with the shared template.
- `Infrastructure adapter implemented`: Bicep compiles and can be selected, but end-to-end benchmark is not yet validated.
- `Experimental scaffold`: provided for future work; high-cost or requires manual external dependencies.
- `Roadmap`: listed because Fabric supports it, but no repo implementation exists yet.

