import pyarrow as pa
import pyarrow.flight as flight
from typing import Dict

class DataFlightServer(flight.FlightServerBase):
    """Apache Arrow Flight RPC server for high-speed zero-copy inter-pod data streaming."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8815, **kwargs):
        location = f"grpc://{host}:{port}"
        super(DataFlightServer, self).__init__(location, **kwargs)
        self.tables: Dict[str, pa.Table] = {}

    def register_table(self, descriptor_key: str, table: pa.Table):
        self.tables[descriptor_key] = table

    def do_get(self, context, ticket):
        key = ticket.ticket.decode("utf-8")
        if key in self.tables:
            table = self.tables[key]
            return flight.RecordBatchStream(table)
        raise flight.FlightServerError(f"Table ticket '{key}' not found")

    def list_flights(self, context, criteria):
        for key, table in self.tables.items():
            descriptor = flight.FlightDescriptor.for_path(key)
            endpoints = [flight.FlightEndpoint(ticket=flight.Ticket(key.encode("utf-8")), locations=[self.location])]
            yield flight.FlightInfo(table.schema, descriptor, endpoints, table.num_rows, table.nbytes)

class DataFlightClient:
    """Client for pulling Arrow batches from remote Flight Servers."""

    def __init__(self, flight_url: str):
        self.client = flight.FlightClient(flight_url)

    def get_table(self, ticket_key: str) -> pa.Table:
        ticket = flight.Ticket(ticket_key.encode("utf-8"))
        reader = self.client.do_get(ticket)
        return reader.read_all()
