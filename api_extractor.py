import json
from typing import Dict, Any, List, Set

class APIExtractor:
    def __init__(self, api_file: str):
        self.api_file = api_file
        self.data = self._load_jsonl()
        # index for fast searching
        self.title_map = {item["title"]: item for item in self.data}

    def _load_jsonl(self) -> List[Dict[str, Any]]:
        result = []
        with open(self.api_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                result.append(json.loads(line))
        return result

    def find_by_title_contains(self, keyword: str) -> Dict[str, Any]:
        for item in self.data:
            if keyword in item["title"]:
                return item
        raise ValueError(f"API not found: {keyword}")

    def parse_ref(self, ref: str) -> str:
        # example: "#/definitions/alps.UserLoginRequest"
        cleaned = ref.lstrip("#/")  # remove leading "#/" 
        cleaned = cleaned.replace("/", ".")  # replace path-style with dotted-style
        return cleaned

    def find_definition(self, def_name: str) -> Dict[str, Any]:
        """Search jsonl where title contains definitions/..."""
        for item in self.data:
            if def_name in item["title"]:
                return item
        raise ValueError(f"Definition not found: {def_name}")

    def extract_parameters(self, node: Any, visited: Set[str] = None) -> List[Dict[str, Any]]:
        """Recursively parse parameters (input fields)."""

        if visited is None:
            visited = set()

        params = []

        if isinstance(node, list):
            for item in node:
                params.extend(self.extract_parameters(item, visited))
            return params

        if not isinstance(node, dict):
            return params

        # Direct basic parameter
        if "$ref" in node:
            ref = self.parse_ref(node["$ref"])
            if ref in visited:
                return []  # avoid infinite recursion
            visited.add(ref)

            def_obj = self.find_definition(ref)
            content = json.loads(def_obj["content"])
            # definitions always stored something like {"type":"object", "properties":{...}}
            properties = content.get("properties", {})
            for name, val in properties.items():
                params.extend(self.extract_parameters({"name": name, **val}, visited))
            return params

        # Normal param structure
        name = node.get("name")
        type_ = node.get("type")
        if name:
            params.append({
                "name": name,
                "type": type_ or node.get("$ref", "object"),
                "required": node.get("required", False),
                "description": node.get("description", "")
            })

        # If schema exists, parse schema
        if "schema" in node:
            params.extend(self.extract_parameters(node["schema"], visited))

        # If properties exist (definition)
        if "properties" in node:
            for name, val in node["properties"].items():
                params.extend(self.extract_parameters({"name": name, **val}, visited))

        return params

    def extract_output(self, responses: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse output parameters from responses['200'] schema."""
        if "200" not in responses:
            return []

        schema = responses["200"].get("schema")
        if not schema:
            return []

        return self.extract_parameters(schema)

    def extract_api(self, path_keyword: str) -> Dict[str, Any]:
        api_item = self.find_by_title_contains(path_keyword)
        api_content = json.loads(api_item["content"])

        # e.g. "paths./v1/cl/user/login"
        api_description = api_content.get("post", {}).get("summary", "")
        api_path = api_content.get("name", "")

        # parameters
        params = api_content.get("post", {}).get("parameters", [])
        input_params = self.extract_parameters(params)

        # output
        responses = api_content.get("post", {}).get("responses", {})
        output_params = self.extract_output(responses)

        return {
            "description": api_description,
            "path": api_path.replace("paths.", "/"),  # normalize
            "input": input_params,
            "output": output_params
        }

    def save_result(self, result: Dict[str, Any], out_file: str):
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    extractor = APIExtractor("inputs/xrt_openapi.jsonl")

    # 你想查询的 API
    api_path = "/v1/cl/testcase/save"

    result = extractor.extract_api(api_path)

    extractor.save_result(result, "output.json")

    print("Done. Result saved to output.json")
