// Smoke call for the oapi-codegen client: GET /fixtures.
package main

import (
	"context"
	"fmt"
	"net/http"
	"os"

	ltapi "github.com/livetennisapi/gen-oapi"
)

func main() {
	auth := func(_ context.Context, req *http.Request) error {
		req.Header.Set("Authorization", "Bearer test-key")
		return nil
	}
	client, err := ltapi.NewClientWithResponses(os.Args[1], ltapi.WithRequestEditorFn(auth))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	limit := 3
	resp, err := client.ListFixturesWithResponse(context.Background(), &ltapi.ListFixturesParams{Limit: &limit})
	if err != nil || resp.JSON200 == nil || resp.JSON200.Data == nil {
		fmt.Fprintf(os.Stderr, "call failed: %v status=%d\n", err, resp.StatusCode())
		os.Exit(1)
	}
	rows := *resp.JSON200.Data
	if len(rows) != 3 || rows[0].Tournament == nil || *rows[0].Tournament != "Rome" {
		fmt.Fprintf(os.Stderr, "unexpected page: %s\n", resp.Body)
		os.Exit(1)
	}
	fmt.Printf("oapi-codegen smoke ok: %d fixtures, first %s v %s\n", len(rows), *rows[0].Player1Name, *rows[0].Player2Name)
}
