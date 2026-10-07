# Transactional work and in-process events

Persist required audit and outbound delivery work inside the originating transaction, then publish in-process events after commit. In-process/realtime publication is best effort and has no durable replay; durable delivery uses database queues with at-least-once semantics rather than introducing a message broker.
