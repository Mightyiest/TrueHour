class BaseExporter:
    def export(self, report_data: dict, output_path: str) -> bool:
        raise NotImplementedError("Exporters must implement export()")
