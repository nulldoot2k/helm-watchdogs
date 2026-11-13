// Package watchdogs implements the native Vault seal wrapper used by the
// Vault Watchdogs Edition. It talks only to the Watchdogs key service API.
package watchdogs

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	wrapping "github.com/hashicorp/go-kms-wrapping/v2"
)

const wrapperType wrapping.WrapperType = "watchdogs"

type Wrapper struct {
	address string
	token   string
	keyID   string
	client  *http.Client
}

type response struct {
	KeyID         string `json:"key_id"`
	Version       int    `json:"version"`
	CiphertextHex string `json:"ciphertext_hex"`
	PlaintextHex  string `json:"plaintext_hex"`
	Error         string `json:"error"`
}

func NewWrapper() *Wrapper { return &Wrapper{client: &http.Client{Timeout: 5 * time.Second}} }

func (w *Wrapper) Type(context.Context) (wrapping.WrapperType, error) { return wrapperType, nil }

func (w *Wrapper) KeyId(context.Context) (string, error) {
	if w.keyID == "" {
		return "", fmt.Errorf("watchdogs key_id is not configured")
	}
	return w.keyID, nil
}

func (w *Wrapper) SetConfig(ctx context.Context, options ...wrapping.Option) (*wrapping.WrapperConfig, error) {
	opts, err := wrapping.GetOpts(options...)
	if err != nil {
		return nil, err
	}
	config := opts.WithConfigMap
	w.address = strings.TrimRight(config["address"], "/")
	w.token = config["token"]
	if file := config["token_file"]; file != "" {
		data, readErr := os.ReadFile(file)
		if readErr != nil {
			return nil, fmt.Errorf("read watchdogs token_file: %w", readErr)
		}
		w.token = strings.TrimSpace(string(data))
	}
	w.keyID = config["key_id"]
	if w.address == "" || w.keyID == "" || w.token == "" {
		return nil, fmt.Errorf("watchdogs seal requires address, key_id and token or token_file")
	}
	if strings.HasPrefix(w.address, "https://") {
		transport := &http.Transport{}
		tlsConfig := &tls.Config{MinVersion: tls.VersionTLS12}
		if caFile := config["ca_file"]; caFile != "" {
			caData, readErr := os.ReadFile(caFile)
			if readErr != nil {
				return nil, fmt.Errorf("read watchdogs ca_file: %w", readErr)
			}
			pool, poolErr := x509.SystemCertPool()
			if poolErr != nil || pool == nil {
				pool = x509.NewCertPool()
			}
			if !pool.AppendCertsFromPEM(caData) {
				return nil, fmt.Errorf("watchdogs ca_file contains no certificates")
			}
			tlsConfig.RootCAs = pool
		}
		certFile, keyFile := config["client_cert_file"], config["client_key_file"]
		if certFile == "" || keyFile == "" {
			return nil, fmt.Errorf("watchdogs mTLS requires client_cert_file and client_key_file")
		}
		cert, certErr := tls.LoadX509KeyPair(certFile, keyFile)
		if certErr != nil {
			return nil, fmt.Errorf("load watchdogs client certificate: %w", certErr)
		}
		tlsConfig.Certificates = []tls.Certificate{cert}
		transport.TLSClientConfig = tlsConfig
		w.client = &http.Client{Transport: transport, Timeout: 5 * time.Second}
	}
	return &wrapping.WrapperConfig{Metadata: map[string]string{
		"address": w.address, "key_id": w.keyID,
	}}, nil
}

func (w *Wrapper) Encrypt(ctx context.Context, plaintext []byte, options ...wrapping.Option) (*wrapping.BlobInfo, error) {
	if err := w.ensure(ctx); err != nil {
		return nil, err
	}
	var opts *wrapping.Options
	var err error
	if opts, err = wrapping.GetOpts(options...); err != nil {
		return nil, err
	}
	request := map[string]string{"plaintext_hex": hex.EncodeToString(plaintext)}
	if len(opts.WithAad) > 0 {
		request["aad_hex"] = hex.EncodeToString(opts.WithAad)
	}
	var result response
	if err := w.post(ctx, "/v1/keys/"+w.keyID+"/encrypt", request, &result); err != nil {
		return nil, err
	}
	ciphertext, err := hex.DecodeString(result.CiphertextHex)
	if err != nil {
		return nil, fmt.Errorf("watchdogs returned invalid ciphertext: %w", err)
	}
	return &wrapping.BlobInfo{Ciphertext: ciphertext, KeyInfo: &wrapping.KeyInfo{KeyId: fmt.Sprintf("%s:%d", w.keyID, result.Version)}}, nil
}

func (w *Wrapper) Decrypt(ctx context.Context, ciphertext *wrapping.BlobInfo, options ...wrapping.Option) ([]byte, error) {
	if err := w.ensure(ctx); err != nil {
		return nil, err
	}
	var result response
	if err := w.post(ctx, "/v1/keys/"+w.keyID+"/decrypt", map[string]string{"ciphertext_hex": hex.EncodeToString(ciphertext.Ciphertext)}, &result); err != nil {
		return nil, err
	}
	plaintext, err := hex.DecodeString(result.PlaintextHex)
	if err != nil {
		return nil, fmt.Errorf("watchdogs returned invalid plaintext: %w", err)
	}
	return plaintext, nil
}

func (w *Wrapper) ensure(ctx context.Context) error {
	var result response
	return w.post(ctx, "/v1/keys/ensure", map[string]string{"key_id": w.keyID}, &result)
}

func (w *Wrapper) post(ctx context.Context, path string, payload map[string]string, result *response) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, w.address+path, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+w.token)
	req.Header.Set("Content-Type", "application/json")
	resp, err := w.client.Do(req)
	if err != nil {
		return fmt.Errorf("watchdogs key service request: %w", err)
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err := json.Unmarshal(data, result); err != nil {
		return fmt.Errorf("watchdogs key service response: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("watchdogs key service: %s", result.Error)
	}
	return nil
}
