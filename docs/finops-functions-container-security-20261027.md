# Functions container security exception — 2026-10-27

Scope: only CKV_DOCKER_3 on services/usage-ingestion/Dockerfile, with the
unchanged pinned Microsoft Python Functions base 4.1055.150-0-python3.11.
This is an explicitly reported compatibility exception, NOT a fixed finding
or a claim that Azure Functions universally requires root. The approved bounded
repair preserves the existing runtime user and introduces no privilege widening.

Microsoft's official custom-container template supports non-root operation only
after preparing writable /home, /local, /tmp/metrics and host Secrets paths.
Its separate SSH startup requires root. This image does not opt into SSH or the
appservice variant. Non-root startup for this exact prebuilt Python image and
the existing port-80 App Service configuration has not been validated; blindly
adding USER 10001, broad chmod/chown, changing ports or replacing the host is not
part of this urgent image-only release. No claim of an inherent root requirement.

References consulted:
- https://learn.microsoft.com/en-us/azure/azure-functions/functions-how-to-custom-container
- https://github.com/Azure/azure-functions-docker/blob/dev/custom-container/template.Dockerfile

Compensating controls retained: exact immutable image, no seeding/migrations at
startup, selected least-privilege managed identity, private PostgreSQL with zero
public rules, unchanged private API/SCM/ingress/TLS and registry identity, timer
disabled until runtime readiness. Code is packaged at build time; a read-only
root filesystem is NOT claimed. Future non-root migration requires a separately
tested runtime change, not a fictional pass for this check.

CKV_DOCKER_2 is addressed by an explicit bounded localhost TCP port-80 liveness
probe, tested in the native Linux build. It performs no DB query or authenticated
HTTP call and is not proof of Functions discovery, MI, storage or ingestion health.
The scanner must report zero failed checks and exactly this one skipped check;
all other checks remain enforced. The prior 78-pass/2-fail report is retained.