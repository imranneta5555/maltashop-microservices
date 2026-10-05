# MaltaShop microservices prototype

Unit 5: Service-Oriented Architecture and Microservices Fundamentals.

A small prototype of the "place an order" flow for MaltaShop Ltd, the case study in the
assignment brief. Work in progress: the Order and Notification services are being built
one step at a time.

## Planned

- `order-service`: REST API that accepts orders and owns the order database (PostgreSQL)
- `notification-service`: consumes the `OrderPlaced` event and owns its own store (MongoDB)
- RabbitMQ as the message broker between them
- One `docker compose up` to start everything
