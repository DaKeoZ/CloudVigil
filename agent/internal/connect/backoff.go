// Package connect gère la reconnexion gRPC avec un backoff exponentiel plafonné.
package connect

import (
	"context"
	"log"
	"math"
	"time"
)

const (
	// InitialDelay est le délai avant la première tentative de reconnexion.
	InitialDelay = 1 * time.Second
	// MaxDelay plafonne l'attente entre deux tentatives.
	MaxDelay = 60 * time.Second
	// Multiplier est le facteur appliqué à chaque tentative.
	Multiplier = 2.0
	// JitterFraction ajoute ±10 % d'aléatoire pour éviter les tempêtes de reconnexion.
	JitterFraction = 0.1
)

// Policy encapsule la stratégie de backoff exponentiel.
type Policy struct {
	attempt int
}

// Reset remet le compteur à zéro (connexion réussie).
func (p *Policy) Reset() {
	p.attempt = 0
}

// Next calcule le prochain délai d'attente et incrémente le compteur.
// La formule est : min(InitialDelay * Multiplier^attempt, MaxDelay) ± jitter.
func (p *Policy) Next() time.Duration {
	raw := float64(InitialDelay) * math.Pow(Multiplier, float64(p.attempt))
	if raw > float64(MaxDelay) {
		raw = float64(MaxDelay)
	}

	// Jitter symétrique : ±10 % de la valeur calculée.
	jitter := raw * JitterFraction * (2*pseudoRandFloat() - 1)
	delay := time.Duration(raw + jitter)

	p.attempt++
	return delay
}

// Wait bloque pendant la durée calculée, ou retourne immédiatement si ctx est annulé.
// Retourne false si le contexte a été annulé pendant l'attente.
func (p *Policy) Wait(ctx context.Context) bool {
	d := p.Next()
	log.Printf("[backoff] tentative %d — nouvelle connexion dans %s", p.attempt, d.Round(time.Millisecond))
	select {
	case <-time.After(d):
		return true
	case <-ctx.Done():
		return false
	}
}

// pseudoRandFloat retourne un float64 dans [0, 1) basé sur l'heure nano.
// Pas cryptographiquement sûr, mais suffisant pour le jitter.
func pseudoRandFloat() float64 {
	ns := float64(time.Now().UnixNano())
	return math.Mod(ns/1e9, 1.0)
}
