package com.example.DyslexiLearn.controllers;

import com.example.DyslexiLearn.models.Flashcard;
import com.example.DyslexiLearn.services.FlashcardService;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/flashcards")
public class FlashcardsController {

    @Autowired
    private FlashcardService flashcardService;
    private FlashcardService flashcardService;
    // Create a new flashcard
    @PostMapping
    public ResponseEntity<Flashcard> createFlashcard(@RequestBody Flashcard flashcard) {
        try {
            Flashcard createdFlashcard = flashcardService.createFlashcard(flashcard);
            return ResponseEntity.ok(createdFlashcard);
        return ResponseEntity.ok(createdFlashcard);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(null);
        }
    }

    // Get all flashcards
    @GetMapping
    public ResponseEntity<List<Flashcard>> getAllFlashcards() {
        List<Flashcard> flashcards = flashcardService.getAllFlashcards();
        return ResponseEntity.ok(flashcards);
    }

    // Update an existing flashcard by ID
    @PutMapping("/{id}")
    public ResponseEntity<Flashcard> updateFlashcard(
            @PathVariable Long id,
            @RequestBody Flashcard updatedFlashcard) {
        try {
            Flashcard flashcard = flashcardService.updateFlashcard(id, updatedFlashcard);
            return ResponseEntity.ok(flashcard);
        } catch (Exception e) {
            return ResponseEntity.notFound().build(); // Return 404 if not found
        }
    }

    // Delete a flashcard by ID
    @DeleteMapping("/{id}")
    public ResponseEntity<String> deleteFlashcard(@PathVariable Long id) {
        try {
            flashcardService.deleteFlashcard(id);
            return ResponseEntity.ok("Flashcard deleted successfully!");
        } catch (Exception e) {
            return ResponseEntity.notFound().build(); // Return 404 if not found
        }
    }
}