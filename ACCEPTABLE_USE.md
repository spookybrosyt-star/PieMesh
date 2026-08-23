# Piemesh Acceptable Use Policy

## Who may use this
Anyone who owns the machine they install the agent on, and who uses
the mesh exclusively against targets whose ownership has been proven
via DNS TXT challenge on their hub.

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
- Closing the window stops all activity instantly
- `python agent.py --revoke-consent` wipes your identity and consent records
- You are responsible for the accuracy of your consent and for the machine you enroll

## Reporting abuse
Contact the hub operator listed in their distribution. If the operator
is unreachable or complicit, stop running the agent and revoke consent.
