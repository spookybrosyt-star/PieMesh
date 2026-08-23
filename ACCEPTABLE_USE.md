# Piemesh Acceptable Use Policy

## Who may use this
Anyone who owns the machine they install the agent on, and who uses
the mesh exclusively against targets whose ownership has been proven
via DNS TXT challenge on their hub.

There is no spectator mode. Everyone who runs PieMesh contributes an
agent node - members, testers, and hub operators on their own
deployments alike. Contributing earns capability, not exemption:
every member's tests require verified targets.

## Prohibited
- Load generation against any system without verified ownership or written authorization
- Removing, patching, or bypassing DNS verification, resource caps, or audit logging
- Operating a hub without maintaining audit logs (minimum 90 days retention)
- Enrolling machines you do not control
- Using the mesh as a front for harassment, extortion, competition sabotage, or booter services

## Hub operator duties
1. Keep target verification ENFORCED on your deployment - it is the load-bearing control
2. Retain `audit.log` and `targets.json` for at least 90 days
3. Provide an abuse contact in your fork's README
4. Respond substantively to abuse reports within 72 hours
5. Publish your verification-enforcement status honestly - volunteers trust YOUR deployment

## Volunteer protections and duties
- Resource caps are compiled into your agent and cannot be raised remotely
- Closing the window (or tray **Exit**) stops the running node instantly
- **Start with Windows** is opt-in and off by default. If you enable it,
  the node rejoins the mesh and resumes contributing load-testing capacity
  on every boot — without re-prompting — until you disable it via the tray
  toggle or `python agent.py --uninstall-autostart`. Enable it only on a
  machine you own and intend to keep in the mesh unattended
- `python agent.py --revoke-consent` wipes your identity and consent records
- You are responsible for the accuracy of your consent and for the machine you enroll

## Reporting abuse
Contact the hub operator listed in their distribution. If the operator
is unreachable or complicit, stop running the agent and revoke consent.
