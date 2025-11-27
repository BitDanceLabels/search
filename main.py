from vespa.package import (
    ApplicationPackage,
    Field,
    Schema,
    Document,
    RankProfile,
    FieldSet,
    Function
)
from vespa.deployment import VespaDocker
from vespa.io import VespaResponse
from datasets import load_dataset
from tqdm import tqdm

package = ApplicationPackage(
    name="simplesearch",
    schema=[
        Schema(
            name="doc",
            document=Document(
                fields=[
                    Field(name="id", type="string", indexing=["summary"]),
                    Field(name="text", type="string", indexing=["index", "summary"], index="enable-bm25"),
                    Field(name="url", type="string", indexing=["index","summary"]),
                ]
            ),
            fieldsets=[
                FieldSet(name="default", fields=["text", "url"]),
            ],
            rank_profiles=[
                RankProfile(
                    name="bm25", 
                    functions=[
                        Function(name="bm25texturl", expression="bm25(text) + 0.1 * bm25(url)"),
                    ],
                    first_phase="bm25texturl",
                )
            ],
        ),
    ]
)

vespa_docker = VespaDocker()
app = vespa_docker.deploy(application_package=package)

dataset = load_dataset("HuggingFaceFW/fineweb", "CC-MAIN-2025-26", split="train", streaming=True).take(1000)
vespa_feed = dataset.map(lambda x: {
    "id": x["id"],
    "fields": {
        "text": x["text"],
        "url": x["url"],
        "id": x["id"],
    }
})

pbar = tqdm(desc="Feeding documents", unit="docs")
feed_count = {"success": 0, "error": 0}
def callback(response: VespaResponse, id: str):
    if response.is_successful():
        feed_count["success"] += 1
    else:
        feed_count["error"] += 1
        pbar.write(f"Error when feeding document {id}: {response.get_json()}")
    pbar.update(1)

app.feed_iterable(vespa_feed, schema="doc", callback=callback)
pbar.close()
