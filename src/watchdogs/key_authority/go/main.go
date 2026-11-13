package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/hashicorp/raft"
	bolt "github.com/hashicorp/raft-boltdb/v2"
)

type keyRecord struct {
	KeyID      string `json:"key_id"`
	Version    int    `json:"version"`
	State      string `json:"state"`
	Nonce      []byte `json:"nonce"`
	Ciphertext []byte `json:"ciphertext"`
}
type raftCommand struct {
	Record keyRecord `json:"record"`
}

type authority struct {
	mu      sync.RWMutex
	root    []byte
	records map[string]keyRecord
	raft    *raft.Raft
	token   string
}

func (a *authority) Apply(logEntry *raft.Log) interface{} {
	var command raftCommand
	if err := json.Unmarshal(logEntry.Data, &command); err != nil {
		return err
	}
	a.mu.Lock()
	a.records[command.Record.KeyID] = command.Record
	a.mu.Unlock()
	return nil
}
func (a *authority) Snapshot() (raft.FSMSnapshot, error) {
	a.mu.RLock()
	defer a.mu.RUnlock()
	data, err := json.Marshal(a.records)
	return stateSnapshot(data), err
}
func (a *authority) Restore(reader io.ReadCloser) error {
	defer reader.Close()
	data, err := io.ReadAll(reader)
	if err != nil {
		return err
	}
	var records map[string]keyRecord
	if err := json.Unmarshal(data, &records); err != nil {
		return err
	}
	a.mu.Lock()
	a.records = records
	a.mu.Unlock()
	return nil
}

type stateSnapshot []byte

func (s stateSnapshot) Persist(sink raft.SnapshotSink) error {
	if _, err := sink.Write(s); err != nil {
		sink.Cancel()
		return err
	}
	return sink.Close()
}
func (stateSnapshot) Release() {}

func randomBytes(size int) ([]byte, error) {
	value := make([]byte, size)
	_, err := rand.Read(value)
	return value, err
}
func seal(key, plaintext []byte) ([]byte, []byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, nil, err
	}
	nonce, err := randomBytes(gcm.NonceSize())
	if err != nil {
		return nil, nil, err
	}
	return nonce, gcm.Seal(nil, nonce, plaintext, nil), nil
}
func open(key, nonce, ciphertext []byte) ([]byte, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	return gcm.Open(nil, nonce, ciphertext, nil)
}

func gfMul(left, right byte) byte {
	var result byte
	for i := 0; i < 8; i++ {
		if right&1 != 0 {
			result ^= left
		}
		high := left&0x80 != 0
		left <<= 1
		if high {
			left ^= 0x1b
		}
		right >>= 1
	}
	return result
}
func gfPow(value byte, exponent int) byte {
	result := byte(1)
	for exponent > 0 {
		if exponent&1 != 0 {
			result = gfMul(result, value)
		}
		value = gfMul(value, value)
		exponent >>= 1
	}
	return result
}
func combineShares(shares []string) ([]byte, error) {
	if len(shares) < 2 {
		return nil, errors.New("guardian quorum required")
	}
	type parsed struct {
		threshold, x int
		data         []byte
	}
	parsedShares := make([]parsed, 0, len(shares))
	for _, raw := range shares {
		parts := strings.SplitN(raw, ":", 4)
		if len(parts) != 4 || parts[0] != "v1" {
			return nil, errors.New("invalid guardian share")
		}
		var threshold, x int
		if _, err := fmt.Sscanf(parts[1], "%d", &threshold); err != nil {
			return nil, errors.New("invalid guardian threshold")
		}
		if _, err := fmt.Sscanf(parts[2], "%d", &x); err != nil || x < 1 || x > 255 {
			return nil, errors.New("invalid guardian coordinate")
		}
		data, err := base64.RawURLEncoding.DecodeString(parts[3])
		if err != nil {
			return nil, errors.New("invalid guardian payload")
		}
		parsedShares = append(parsedShares, parsed{threshold, x, data})
	}
	threshold := parsedShares[0].threshold
	if len(parsedShares) < threshold {
		return nil, errors.New("guardian threshold not met")
	}
	result := make([]byte, len(parsedShares[0].data))
	for j, current := range parsedShares {
		coefficient := byte(1)
		for m, other := range parsedShares {
			if j == m {
				continue
			}
			coefficient = gfMul(coefficient, gfMul(byte(other.x), gfPow(byte(other.x)^byte(current.x), 254)))
		}
		for i, value := range current.data {
			result[i] ^= gfMul(value, coefficient)
		}
	}
	return result, nil
}

func (a *authority) unlock(shares []string) error {
	root, err := combineShares(shares)
	if err != nil || len(root) < 32 {
		return errors.New("guardian quorum not met")
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	a.root = append([]byte(nil), root...)
	return nil
}
func (a *authority) locked() bool { a.mu.RLock(); defer a.mu.RUnlock(); return len(a.root) < 32 }
func (a *authority) keyFor(record keyRecord) ([]byte, error) {
	a.mu.RLock()
	defer a.mu.RUnlock()
	if len(a.root) < 32 {
		return nil, errors.New("guardian quorum locked")
	}
	return open(a.root, record.Nonce, record.Ciphertext)
}
func (a *authority) commit(record keyRecord) error {
	data, err := json.Marshal(raftCommand{Record: record})
	if err != nil {
		return err
	}
	return a.raft.Apply(data, 10*time.Second).Error()
}

func (a *authority) authorized(r *http.Request) bool {
	return a.token != "" && r.Header.Get("Authorization") == "Bearer "+a.token
}
func jsonReply(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
func (a *authority) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/healthz" {
		jsonReply(w, 200, map[string]any{"status": "ok", "unlocked": !a.locked(), "leader": a.raft.Leader()})
		return
	}
	if !a.authorized(r) {
		jsonReply(w, 401, map[string]string{"error": "authentication_required"})
		return
	}
	switch {
	case r.Method == http.MethodGet && r.URL.Path == "/v1/status":
		jsonReply(w, 200, map[string]any{"unlocked": !a.locked(), "leader": a.raft.Leader(), "state": a.raft.State().String()})
	case r.Method == http.MethodPost && r.URL.Path == "/v1/unlock":
		var input struct {
			Shares []string `json:"shares"`
		}
		if json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&input) != nil || a.unlock(input.Shares) != nil {
			jsonReply(w, 400, map[string]string{"error": "guardian_quorum_not_met"})
		} else {
			jsonReply(w, 200, map[string]bool{"unlocked": true})
		}
	case r.Method == http.MethodPost && r.URL.Path == "/v1/lock":
		a.mu.Lock()
		for i := range a.root {
			a.root[i] = 0
		}
		a.root = nil
		a.mu.Unlock()
		jsonReply(w, 200, map[string]bool{"unlocked": false})
	case r.Method == http.MethodPost && r.URL.Path == "/v1/raft/join":
		if a.raft.State() != raft.Leader {
			jsonReply(w, 409, map[string]string{"error": "not_leader"})
			return
		}
		var input struct{ ID string `json:"id"`; Address string `json:"address"` }
		if json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(&input) != nil || input.ID == "" || input.Address == "" {
			jsonReply(w, 400, map[string]string{"error": "invalid_join_request"})
			return
		}
		if err := a.raft.AddVoter(raft.ServerID(input.ID), raft.ServerAddress(input.Address), 0, 10*time.Second).Error(); err != nil {
			jsonReply(w, 500, map[string]string{"error": "raft_join_failed"})
			return
		}
		jsonReply(w, 200, map[string]bool{"joined": true})
	case r.Method == http.MethodPost && r.URL.Path == "/v1/keys/ensure":
		a.ensure(w, r)
	case r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/v1/keys/") && strings.HasSuffix(r.URL.Path, "/encrypt"):
		a.crypt(w, r, true)
	case r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/v1/keys/") && strings.HasSuffix(r.URL.Path, "/decrypt"):
		a.crypt(w, r, false)
	default:
		jsonReply(w, 404, map[string]string{"error": "not_found"})
	}
}
func (a *authority) ensure(w http.ResponseWriter, r *http.Request) {
	if a.locked() {
		jsonReply(w, 423, map[string]string{"error": "guardian_quorum_locked"})
		return
	}
	var in struct {
		KeyID string `json:"key_id"`
	}
	if json.NewDecoder(r.Body).Decode(&in) != nil || in.KeyID == "" {
		jsonReply(w, 400, map[string]string{"error": "invalid_key_id"})
		return
	}
	a.mu.RLock()
	record, ok := a.records[in.KeyID]
	a.mu.RUnlock()
	if !ok {
		value, _ := randomBytes(32)
		a.mu.RLock()
		root := append([]byte(nil), a.root...)
		a.mu.RUnlock()
		nonce, ciphertext, err := seal(root, value)
		if err != nil {
			jsonReply(w, 500, map[string]string{"error": "key_generation_failed"})
			return
		}
		record = keyRecord{KeyID: in.KeyID, Version: 1, State: "active", Nonce: nonce, Ciphertext: ciphertext}
		if err := a.commit(record); err != nil {
			jsonReply(w, 500, map[string]string{"error": "raft_commit_failed"})
			return
		}
	}
	jsonReply(w, 200, map[string]any{"key_id": record.KeyID, "version": record.Version, "state": record.State})
}
func (a *authority) crypt(w http.ResponseWriter, r *http.Request, encrypt bool) {
	if a.locked() {
		jsonReply(w, 423, map[string]string{"error": "guardian_quorum_locked"})
		return
	}
	parts := strings.Split(r.URL.Path, "/")
	if len(parts) < 5 {
		jsonReply(w, 400, map[string]string{"error": "invalid_path"})
		return
	}
	keyID := parts[3]
	a.mu.RLock()
	record, ok := a.records[keyID]
	a.mu.RUnlock()
	if !ok {
		jsonReply(w, 404, map[string]string{"error": "key_not_found"})
		return
	}
	key, err := a.keyFor(record)
	if err != nil {
		jsonReply(w, 423, map[string]string{"error": err.Error()})
		return
	}
	var in struct {
		Hex        string `json:"plaintext_hex"`
		Ciphertext string `json:"ciphertext_hex"`
	}
	if json.NewDecoder(r.Body).Decode(&in) != nil {
		jsonReply(w, 400, map[string]string{"error": "invalid_request"})
		return
	}
	if encrypt {
		plaintext, err := hex.DecodeString(in.Hex)
		if err != nil {
			jsonReply(w, 400, map[string]string{"error": "invalid_plaintext"})
			return
		}
		nonce, ciphertext, err := seal(key, plaintext)
		if err != nil {
			jsonReply(w, 500, map[string]string{"error": "encrypt_failed"})
			return
		}
		jsonReply(w, 200, map[string]any{"ciphertext_hex": hex.EncodeToString(append(nonce, ciphertext...)), "key_id": keyID, "version": record.Version})
	} else {
		data, err := hex.DecodeString(in.Ciphertext)
		if err != nil || len(data) < 12 {
			jsonReply(w, 400, map[string]string{"error": "invalid_ciphertext"})
			return
		}
		plaintext, err := open(key, data[:12], data[12:])
		if err != nil {
			jsonReply(w, 400, map[string]string{"error": "decrypt_failed"})
			return
		}
		jsonReply(w, 200, map[string]any{"plaintext_hex": hex.EncodeToString(plaintext), "key_id": keyID, "version": record.Version})
	}
}

func main() {
	dir := getenv("WATCHDOGS_RAFT_DIR", "/var/lib/watchdogs/raft")
	_ = os.MkdirAll(dir, 0700)
	token := os.Getenv("WATCHDOGS_KEY_API_TOKEN")
	if token == "" {
		if path := os.Getenv("WATCHDOGS_KEY_API_TOKEN_FILE"); path != "" {
			if data, readErr := os.ReadFile(path); readErr == nil {
				token = strings.TrimSpace(string(data))
			}
		}
	}
	a := &authority{records: map[string]keyRecord{}, token: token}
	config := raft.DefaultConfig()
	config.LocalID = raft.ServerID(getenv("WATCHDOGS_RAFT_ID", getenv("HOSTNAME", "watchdogs-0")))
	store, err := bolt.NewBoltStore(filepath.Join(dir, "raft.db"))
	if err != nil {
		log.Fatal(err)
	}
	snap, err := raft.NewFileSnapshotStore(dir, 2, os.Stderr)
	if err != nil {
		log.Fatal(err)
	}
	bindAddress := getenv("WATCHDOGS_RAFT_BIND", "0.0.0.0:8300")
	advertiseAddress, err := resolveAdvertise(getenv("WATCHDOGS_RAFT_ADVERTISE", bindAddress))
	if err != nil { log.Fatal(err) }
	transport, err := raft.NewTCPTransport(bindAddress, advertiseAddress, 3, 10*time.Second, os.Stderr)
	if err != nil {
		log.Fatal(err)
	}
	a.raft, err = raft.NewRaft(config, a, store, store, snap, transport)
	if err != nil {
		log.Fatal(err)
	}
	if os.Getenv("WATCHDOGS_RAFT_BOOTSTRAP") == "true" && strings.HasSuffix(string(config.LocalID), "-0") {
		addr := raft.ServerAddress(getenv("WATCHDOGS_RAFT_ADVERTISE", getenv("WATCHDOGS_RAFT_BIND", "watchdogs-0:8300")))
		_ = a.raft.BootstrapCluster(raft.Configuration{Servers: []raft.Server{{ID: config.LocalID, Address: addr}}})
	}
	server := &http.Server{Addr: getenv("KEY_SERVICE_ADDR", ":8090"), Handler: a}
	if join := os.Getenv("WATCHDOGS_RAFT_JOIN_HTTP"); join != "" && !strings.HasSuffix(string(config.LocalID), "-0") {
		go joinRaft(a, join, string(config.LocalID), string(transport.LocalAddr()))
	}
	if cert := os.Getenv("KEY_SERVICE_TLS_CERT_FILE"); cert != "" {
		server.TLSConfig = &tls.Config{MinVersion: tls.VersionTLS12}
		if caPath := os.Getenv("KEY_SERVICE_TLS_CA_FILE"); caPath != "" {
			caData, readErr := os.ReadFile(caPath)
			if readErr != nil { log.Fatal(readErr) }
			pool := x509.NewCertPool()
			if !pool.AppendCertsFromPEM(caData) { log.Fatal("invalid key service CA") }
			server.TLSConfig.ClientCAs = pool
			server.TLSConfig.ClientAuth = tls.RequireAndVerifyClientCert
		}
		log.Fatal(server.ListenAndServeTLS(cert, os.Getenv("KEY_SERVICE_TLS_KEY_FILE")))
	}
	log.Fatal(server.ListenAndServe())
}

func joinRaft(a *authority, endpoint, id, address string) {
	for attempt := 0; attempt < 60; attempt++ {
		if a.raft.State() == raft.Leader { return }
		payload, _ := json.Marshal(map[string]string{"id": id, "address": address})
		req, _ := http.NewRequest(http.MethodPost, strings.TrimRight(endpoint, "/")+"/v1/raft/join", strings.NewReader(string(payload)))
		req.Header.Set("Authorization", "Bearer "+a.token)
		req.Header.Set("Content-Type", "application/json")
		if response, err := http.DefaultClient.Do(req); err == nil { response.Body.Close(); if response.StatusCode == http.StatusOK { return } }
		time.Sleep(2 * time.Second)
	}
	log.Printf("raft join did not complete")
}
func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func resolveAdvertise(address string) (*net.TCPAddr, error) {
	var last error
	for attempt := 0; attempt < 30; attempt++ {
		resolved, err := net.ResolveTCPAddr("tcp", address)
		if err == nil { return resolved, nil }
		last = err
		time.Sleep(time.Second)
	}
	return nil, fmt.Errorf("resolve raft advertise address %q: %w", address, last)
}
