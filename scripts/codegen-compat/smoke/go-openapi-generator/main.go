// Smoke call for the openapi-generator go client: GET /fixtures.
package main

import (
	"context"
	"fmt"
	"os"

	ltapi "github.com/livetennisapi/gen-go"
)

func main() {
	cfg := ltapi.NewConfiguration()
	cfg.Servers = ltapi.ServerConfigurations{{URL: os.Args[1]}}
	ctx := context.WithValue(context.Background(), ltapi.ContextAccessToken, "test-key")
	page, _, err := ltapi.NewAPIClient(cfg).DefaultAPI.ListFixtures(ctx).Limit(3).Execute()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	row := page.Data[0]
	if row.GetTournament() != "Rome" || len(page.Data) != 3 {
		fmt.Fprintf(os.Stderr, "unexpected page: %+v\n", page)
		os.Exit(1)
	}
	fmt.Printf("go (openapi-generator) smoke ok: %d fixtures, first %s v %s\n",
		len(page.Data), row.GetPlayer1Name(), row.GetPlayer2Name())
}
